FROM python:3.4.9-alpine3.8

# install requirements
ADD requirements.txt setup.cfg ./
RUN pip install --no-cache-dir -r requirements.txt

# install asserts
ADD assets/ /opt/resource/

