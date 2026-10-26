FROM rg.fr-par.scw.cloud/djnd/parladata-slovenija:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ \
    pkg-config \
    libpoppler-cpp-dev \
    locales \
    locales-all \
    && rm -rf /var/lib/apt/lists/*

RUN /usr/local/bin/python -m pip install --upgrade pip

RUN mkdir /parser
WORKDIR /parser

COPY requirements.txt /parser/
RUN pip install -r requirements.txt

COPY . /parser

CMD bash run_nightly_parser_flow.sh
