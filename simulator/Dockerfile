FROM python:3.8-alpine as base                                                                                                
                                                                                                                              
FROM base as builder                                                                                                          
                                                                                                                              
RUN mkdir /install                                                                                                            
RUN apk update && apk add postgresql-dev gcc python3-dev musl-dev                                                             
WORKDIR /install                                                                                                              
COPY requirements.txt /requirements.txt
RUN pip install --prefix=/install -r /requirements.txt

FROM base

COPY --from=builder /install /usr/local
COPY requirements.txt /
RUN pip install -r requirements.txt
RUN apk --no-cache add libpq  
ADD . /simulator
WORKDIR /simulator
CMD ["python", "main.py"]
