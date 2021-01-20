## rancher node autoscale by webhook

ENV
```bash
TOKEN = SECRET_TOKEN
RANCHER_NODEPOOL_URL = https://rancher.company.com/v3/nodePools/c-bsptc:np-4bc8r
RANCHER_VERIFY_SSL = 0 #0 by default
RANCHER_TOKEN = token-8gekp:vqxk672fs6788dvqps6jb89n4cgbfbcf7qf64qsb4b7ztpszhbq5lb
RANCHER_VM_MAX = 5 #defaults to 10
MIN_NODE_AGE_SECS = 3600 #how old the node must be in seconds before it can be deleted, 600 gets subtracted from this to include vender overhead of creating the vm.
DRAIN_NODE = false #default to false
```

If DRAIN_NODE is set to true, nodes will be drained.
If false, nodes will be cordoned.

If DRAIN_NODE is set to true, the following vars are used
`IGNORE_DAEMONSETS`
`FORCE_NODE_REMOVAL`
`DELETE_LOCAL_DATA`
All default to false, set to true as need in the ENV VARS.

webhook scale up
```
curl -XPOST http://service:8080/up/SECRET_TOKEN
```
webhook scale down
```
curl -XPOST http://service:8080/down/SECRET_TOKEN
```
