FROM rg.fr-par.scw.cloud/djnd/parladata-slovenija:latest

RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get -y install locales locales-all

RUN /usr/local/bin/python -m pip install --upgrade pip

RUN mkdir /parser
WORKDIR /parser

COPY requirements.txt /parser/
RUN pip install -r requirements.txt

COPY . /parser

CMD bash run_nightly_parser_flow.sh
