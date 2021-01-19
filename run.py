import os
import time

import aiohttp
import time
from japronto import Application

TOKEN = os.getenv('TOKEN', 'SECRET_TOKEN')
RANCHER_NODEPOOL_URL = os.getenv('RANCHER_NODEPOOL_URL', None)
RANCHER_VERIFY_SSL = bool(int(os.getenv('RANCHER_VERIFY_SSL', '0')))
RANCHER_TOKEN = os.getenv('RANCHER_TOKEN', None)
RANCHER_CORDONED_CPU = int(os.getenv('RANCHER_CORDONED_CPU', '20'))
RANCHER_VM_MAX = int(os.getenv('RANCHER_VM_MAX', '10'))
RANCHER_VM_MIN = int(os.getenv('RANCHER_VM_MIN', '0'))
IGNORE_DAEMONSETS = str(os.getenv('IGNORE_DAEMONSETS', 'false'))
FORCE_NODE_REMOVAL = str(os.getenv('FORCE_NODE_REMOVAL', 'false'))
DELETE_LOCAL_DATA = str(os.getenv('DELETE_LOCAL_DATA', 'false'))
DRAIN_NODE = str(os.getenv('DRAIN_NODE', 'false'))
if RANCHER_NODEPOOL_URL is None:
	print("please set env 'RANCHER_NODEPOOL_URL'")


async def try_uncordon_node_of_nodepool(nodes):
	global RANCHER_TOKEN
	global RANCHER_VERIFY_SSL
	async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=RANCHER_VERIFY_SSL),
									 headers={"Authorization": f"Bearer {RANCHER_TOKEN}"}) as session:
		async with session.get(f'{nodes}&order=desc&sort=state') as resp:
			print(f"Attempting to add node. Get node pool rancher api status: {resp.status}")
			list_nodes = await resp.json()
			for node in list_nodes['data']:
				if node['transitioning'] == "yes":
					print('Found transitioning node')
					return True
				if node['state'] == "drained" or node['state'] == "cordoned":
					async with session.post(node['actions']['uncordon']) as resp:
						print(f"uncordon node rancher api status: {resp.status}")
						uncordon = await resp.text()
						return True
	return False


async def try_cordon_last_node_of_nodepool(nodes, hostname_prefix):
	global RANCHER_TOKEN
	global RANCHER_VERIFY_SSL
	global RANCHER_VM_MIN
	async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=RANCHER_VERIFY_SSL),
									 headers={"Authorization": f"Bearer {RANCHER_TOKEN}"}) as session:
		async with session.get(f'{nodes}&order=desc&sort=hostname') as resp:
			print(f"Attempting to remove node. Get node pool rancher api status: {resp.status}")
			list_nodes = await resp.json()
			# check status if only one VM is transitioning, stop scale down (scaling happened?)
			for node in list_nodes['data']:
				if node['transitioning'] == "yes":
					print('Found transitioning node')
					return True
			node = list_nodes['data'][0]
			print(f"node state: {node['state']}")
			
			#drain node if flag set true
			if DRAIN_NODE:
				if node['state'] == "active":
					drain_payload = { "deleteLocalData": {DELETE_LOCAL_DATA}, "force": {FORCE_NODE_REMOVAL}, "gracePeriod": -1, "ignoreDaemonSets": {IGNORE_DAEMONSETS}, "timeout": '120' }
					async with session.post(node['actions']['drain'], data=drain_payload) as resp:
						print(f"Drain node rancher api status: {resp.status}")
						drain = await resp.text()
						return True
			#otherwise just cordon the node
			else:
				if node['state'] == "active":
					async with session.post(node['actions']['cordon']) as resp:
						print(f"cordon node rancher api status: {resp.status}")
						cordon = await resp.text()
						return True
						
			#calculate node age
			print(f"node creation time: {node['createdTS']}")
			print(f"current time: {time.time()}")
			nodeage = node['createdTS'] - time.time()
			print(f"node age: {nodeage}")
			
			if node['state'] == "drained" or node['state'] == "cordoned":
				# remove cordoned node if < RANCHER_CORDONED_CPU
				capacity = int(node['capacity']['cpu']) * 1000
				requested = int(node['requested']['cpu'].replace("m", ""))
				percent = requested/capacity * 100
				print(f"capacity: {capacity}")
				print(f"requested: {requested}")
				print(f"percent: {percent}")
				if percent <= RANCHER_CORDONED_CPU:
					return False
				else:
					print(f"Node too busy to remove, did it fully drain?")
	return True


async def get_nodepool():
	global RANCHER_NODEPOOL_URL
	global RANCHER_TOKEN
	global RANCHER_VERIFY_SSL
	async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=RANCHER_VERIFY_SSL),
									 headers={"Authorization": f"Bearer {RANCHER_TOKEN}"}) as session:
		async with session.get(RANCHER_NODEPOOL_URL) as resp:
			print(f"rancher api status: {resp.status}")
			return await resp.json()


async def set_nodepool(data):
	global RANCHER_NODEPOOL_URL
	global RANCHER_TOKEN
	global RANCHER_VERIFY_SSL
	async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=RANCHER_VERIFY_SSL),
									 headers={"Authorization": f"Bearer {RANCHER_TOKEN}", "Accept": "application/json",
											  "Content-Type": "application/json"}) as session:
		async with session.put(RANCHER_NODEPOOL_URL, json=data) as resp:
			print(f"rancher api status: {resp.status}")
			return await resp.json()


async def scale_up(request):
	global TOKEN
	global RANCHER_VM_MAX
	if request.match_dict['token'] != TOKEN:
		print(f"token '{request.match_dict['token']}' not valid")
		return request.Response(text='ok')
	pool = await get_nodepool()
	# check if we have Cordoned node
	uncordon_node = await try_uncordon_node_of_nodepool(pool['links']['nodes'])
	if uncordon_node:
		print(f"Not scaling up, waiting for next message...")
		print(f"")
		return request.Response(text='ok')
	old = pool['quantity']
	pool['quantity'] = pool['quantity'] + 1
	# limit maximum VMs
	if RANCHER_VM_MAX + 1 <= pool['quantity']:
		return request.Response(text='ok')
	print(f"scale up {old} --> {pool['quantity']}")
	await set_nodepool(pool)
	return request.Response(text='ok')


async def scale_down(request):
	global TOKEN
	if request.match_dict['token'] != TOKEN:
		print(f"token '{request.match_dict['token']}' not valid")
		return request.Response(text='ok')
	pool = await get_nodepool()
	if pool['quantity'] <= RANCHER_VM_MIN:
		print(f'quantity <= {RANCHER_VM_MIN}')
		return request.Response(text='ok')
	# check if we have Cordoned node
	cordon_node = await try_cordon_last_node_of_nodepool(pool['links']['nodes'], pool['hostnamePrefix'])
	if cordon_node:
		print(f"Not scaling down, waiting for next message...")
		print(f"")
		return request.Response(text='ok')
	old = pool['quantity']
	pool['quantity'] = pool['quantity'] - 1
	print(f"scale down {old} --> {pool['quantity']}")
	await set_nodepool(pool)
	return request.Response(text='ok')


app = Application()
r = app.router
print(f"Starting time {time.time()}"


def home(request):
	return request.Response(text='ok')


r.add_route('/', home, methods=['GET'])
r.add_route('/up/{token}', scale_up, methods=['POST'])
r.add_route('/down/{token}', scale_down, methods=['POST'])

app.run()
