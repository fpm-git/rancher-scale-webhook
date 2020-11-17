FROM python:3



WORKDIR /src

COPY requirements.txt .

COPY *.py .

RUN pip install -r requirements.txt


CMD [ "python", "./run.py" ]

