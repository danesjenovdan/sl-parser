import requests
import xmltodict
import re

from datetime import datetime

from lxml import html


def get_unids(data):
    if isinstance(data, dict):
        children = data.get('UNID')
        return get_unids(children)
    elif isinstance(data, list):
        output = [get_unids(item) for item in data]
        if not output:
            return []
        if isinstance(output[0], list):
            return [item for sublist in output for item in sublist]
        return output
    elif isinstance(data, str):
        return [data.split('|')[1]]


def parse(storage):
    mandate = 'VIII'
    url = f'https://fotogalerija.dz-rs.si/datoteke/opendata/SDZ.XML'
    response = requests.get(url)
    with open(f'parlaparser/files/SDZ.XML', 'wb') as f:
        f.write(response.content)
    with open('parlaparser/files/SDZ.XML', 'rb') as data_file:
        data = xmltodict.parse(data_file, dict_constructor=dict)


    # load type of subjects
    for session in data['SDZ']['SEJA']:
        session_name = session['KARTICA_SEJE']['KARTICA_OZNAKA']
        session_type = session['KARTICA_SEJE']['KARTICA_VRSTA']
        uid = session['KARTICA_SEJE']['UNID'].split('|')

        url = f'https://www.dz-rs.si/wps/portal/Home/seje/izbranaSeja/?mandat={mandate}&seja={session_name}.%20{session_type}&uid={uid}'
        print(session)

        speech_pages = session.get('DOBESEDNI_ZAPISI_SEJE', [])
        speech_unids = get_unids(speech_pages)

        print(speech_unids)
        session = {
            'type': session_type,
            'name': session_name,
            'mandate': mandate
        }

        for speech_unid in speech_unids:
            print(speech_unid)
            speech_url = f'https://www.dz-rs.si/wps/portal/Home/seje/evidenca?mandat={mandate}&type=sz&uid={speech_unid}'
            speeches_content = requests.get(url=speech_url).content
            htree = html.fromstring(speeches_content)
            meta, speeches = parse_speeches(htree)

            save_speeches(session, meta, speeches)

class ParserState(Enum):
    META = 1
    TITLE = 2
    RESULT = 3
    CONTENT = 4
    VOTE = 5
    PRE_TITLE = 6
    REMOTE_VOTING_META = 7
    REMOTE_VOTING = 8


def parse_speeches(content):
    state = ParserState.META
    speaker = None
    content = []
    result = []
    meta = []

    find_person = r'([A-ZČŠŽĆĐ. ]{5,50}){1}(\([A-Za-zđčćžšČĆŽŠŽĐ ]*\)){0,1}(:)?'

    for element in htree.cssselect("span.outputText font"):
        print(element.text)
        print()
        line = element.text.strip()
        if state == ParserState.META:
            if line:
                meta.append(line)
            if line.lower().startswith('seja se je začela'):
                state = ParserState.CONTENT
        elif state == ParserState.CONTENT:
            if element.getparent().tag == 'b':
                person_line = re.findall(find_person, line)
                print(person_line)
                if len(person_line) == 1:
                    if speaker:
                        result.append((speaker, ' '.join(content)))
                        content = []
                    speaker = person_line[0]
                else:
                    # TODO trak magic
                    if line.lower().startswith('seja se je kon'):
                        continue
                    content.append(line)
            else:
                content.append(line)

    result.append((speaker, ' '.join(content)))

    return meta, result

def save_speeches(session_data, meta, speeches):
    pass
    # TODO 

