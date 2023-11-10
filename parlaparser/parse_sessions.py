import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import xmltodict
import re
import locale
import sentry_sdk

from datetime import datetime

from lxml import html
from enum import Enum
from urllib import parse

from parlaparser.settings import BASE_URL, MANDATE, MANDATE_GOV_ID
from parlaparser.utils.methods import get_values
from parlaparser.parse_speeches import SpeechParser
from parlaparser.parse_votes import VotesParser


class ParserState(Enum):
    META = 1
    TITLE = 2
    RESULT = 3
    CONTENT = 4
    VOTE = 5
    PRE_TITLE = 6
    REMOTE_VOTING_META = 7
    REMOTE_VOTING = 8

SESSION_TYPES = {
    'redna': 'regular',
    'izredna': 'irregular',
    'nujna': 'urgent',
}

class SessionParser(object):
    def __init__(self, storage):
        self.storage = storage
        locale.setlocale(locale.LC_TIME, "sl_SI")
        self.documents = {}
        self.magnetograms = {}

    def load_documents(self, data, root_key):
        print('Loading documents')

        for doc in data[root_key]['DOKUMENT']:
            try:
                if 'PRIPONKA' in doc.keys():
                    urls = get_values(doc['PRIPONKA'], 'PRIPONKA_KLIC')
                    self.documents[doc['KARTICA_DOKUMENTA']['UNID']] = {
                        'title': doc['KARTICA_DOKUMENTA']['KARTICA_NASLOV'],
                        'urls': urls
                    }
                elif 'KARTICA_URL_MAGNETOGRAM' in doc['KARTICA_DOKUMENTA']:
                    self.magnetograms[doc['KARTICA_DOKUMENTA']['UNID']] = doc['KARTICA_DOKUMENTA']['KARTICA_URL_MAGNETOGRAM']
            except:
                print(doc)
                raise Exception('key_error')
        self.document_keys = self.documents.keys()

    def parse(self, session_number=None, session_type=None, parse_speeches=False, parse_votes=False):

        session_url_groups = [
            # TODO uncoment for parsing DZ sessions
            {
                'url':'https://fotogalerija.dz-rs.si/datoteke/opendata/SDZ.XML',
                'root_key': 'SDZ',
                'file_name': 'SDZ.XML',
                'dz_url': 'https://www.dz-rs.si/wps/portal/Home/seje/izbranaSeja'
            },
            {
                'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/SDT.XML',
                'root_key': 'SDT',
                'file_name': 'SDT.XML',
                'dz_url': 'https://www.dz-rs.si/wps/portal/Home/seje/izbranaSejaDt'
            }
        ]
        for url_group in session_url_groups:
            response = requests.get(url_group['url'])
            with open(f'/tmp/{url_group["file_name"]}', 'wb') as f:
                f.write(response.content)
            with open(f'/tmp/{url_group["file_name"]}', 'rb') as data_file:
                data = xmltodict.parse(data_file, dict_constructor=dict)

            # load documents from XML
            self.load_documents(data, url_group['root_key'])

            # load type of subjects
            num_of_session = len(data[url_group['root_key']]['SEJA'])
            for index, session in enumerate(list(reversed(data[url_group['root_key']]['SEJA']))):
                print()
                print('New session')
                #print(session['KARTICA_SEJE']['KARTICA_OZNAKA'])
                session_name = session['KARTICA_SEJE']['KARTICA_OZNAKA'].lstrip("0")
                session_type_xml = session['KARTICA_SEJE']['KARTICA_VRSTA']
                organization_name = session['KARTICA_SEJE']['KARTICA_STATUS']
                print(f'parsing session {index}/{num_of_session}')

                start_time = None

                session_needs_editing = False

                if not session_name:
                    print('Session has unvalid name')
                    continue

                try:
                    if (session_number and int(session_name) != int(session_number)) or (session_type and session_type_xml != session_type):
                        print('skip session')
                        continue
                except:
                    continue


                uid = session['KARTICA_SEJE']['UNID'].split('|')[1]

                session_url = f'{url_group["dz_url"]}/?mandat={MANDATE_GOV_ID}&seja= {session_name}.%20{session_type_xml}&uid={uid}'

                print(f'Parsing session with url {session_url}')

                # get session page
                request_session = requests.Session()

                retry = Retry(connect=3, backoff_factor=2)
                adapter = HTTPAdapter(max_retries=retry)
                request_session.mount('http://', adapter)
                request_session.mount('https://', adapter)

                session_page = request_session.get(url=session_url).content
                session_htree = html.fromstring(session_page)

                session_in_review = True

                # check if is "skupna seja"
                title = session_htree.cssselect('form div h2')
                if title:
                    session_name_from_page = title[0].text
                else:
                    print('session without title')
                    continue
                session_needs_editing = True if '(skupna seja)' in session_name_from_page else False

                try:
                    # if there is any speech at the session
                    first_speech_date = session_htree.cssselect('form>div>table>tbody>tr>td>div>table a')[0].text.replace(' ', '').split('Z')[0].strip()
                    start_time = datetime.strptime(first_speech_date, '%d.%m.%Y')
                    session_in_review = False

                    # check if session has any speech document in review
                    for speech_link in session_htree.cssselect('form>div>table>tbody>tr>td>div>table a'):
                        if '(v pregledu)' in speech_link.text:
                            session_in_review = True
                except:
                    pass

                try:
                    # try find date from "Sklic seje" for session start time
                    documents_on_page = session_htree.cssselect('form>div>table>tbody>tr a')
                    if documents_on_page and documents_on_page[0].text == 'Sklic seje':
                        sklic_url = session_htree.cssselect('form>div>table>tbody>tr a')[0].values()[1]
                        sklic_content = requests.get(f'https://www.dz-rs.si{sklic_url}').content
                        sklic_htree = html.fromstring(sklic_content)

                        sklic_start_time = self.find_date_form_table(sklic_htree)
                        if sklic_start_time and not start_time:
                            # if session has not speeches try to find start time from sklic
                            start_time = sklic_start_time
                        elif start_time:
                            # if session has speeches then use date of 1st speech
                            pass
                        else:
                            # TODO sentry call or something. That is wierd case in sklic without date.
                            session_needs_editing = True

                    # skip parsing session with start time in future
                    if start_time > datetime.now():
                        continue

                except Exception as e:
                    print('----ERROR.....:   cannot find date', e)
                    continue

                print(session)

                session_documents = session.get('PODDOKUMENTI', [])
                document_unids = get_values(session_documents)

                speech_pages = session.get('DOBESEDNI_ZAPISI_SEJE', [])
                speech_unids = get_values(speech_pages)

                if organization_name:
                    organization = self.storage.organization_storage.get_or_add_organization(
                        organization_name + ' ' + MANDATE_GOV_ID,
                    )
                    organization_id = organization.id
                else:
                    organization_id = self.storage.main_org_id

                # get or add session
                current_session = self.storage.session_storage.add_or_get_session({
                    'name': f'{session_name}. {session_type_xml.lower()} seja',
                    'organization': organization_id,
                    'organizations': [organization_id],
                    'classification': self.get_session_type(session_type_xml),
                    'start_time': start_time.isoformat(),
                    'in_review': session_in_review,
                    'needs_editing': session_needs_editing,
                    'gov_id': session_url.replace(" ", ""),
                    'mandate_id': self.storage.mandate_id
                })
                session_id = current_session.id
                #if current_session.start_time != start_time.isoformat():
                #    # patch session start_time if is changed on dz page
                #    self.storage.session_storage.patch_session(current_session, {'start_time': start_time.isoformat()})

                print(f'Getted session: {session_name}. {session_type_xml.lower()} seja has id {session_id}')

                parse_all_speeches = False
                parse_new_speeches = False

                was_session_in_review = self.storage.session_storage.is_session_in_review(current_session)

                # session is reviewed, reload speeches
                if not session_in_review and was_session_in_review:
                    # set session to not in review
                    self.storage.session_storage.patch_session(current_session, {'in_review': False})

                    if parse_speeches:
                        # unvalidate speeches
                        current_session.unvalidate_speeches()

                    # TODO parse new speeches
                    parse_all_speeches = True

                elif session_in_review and not was_session_in_review:
                    # set session to not in review
                    self.storage.session_storage.patch_session(current_session, {'in_review': True})
                    parse_new_speeches = True

                elif session_in_review and was_session_in_review:
                    parse_new_speeches = True
                elif current_session.is_new:
                    parse_all_speeches = True


                if current_session.is_new and document_unids:
                    for doc_unid in document_unids:
                        if doc_unid in self.document_keys:
                            document = self.documents[doc_unid]
                            doc_title = document['title']
                            for doc_url in document['urls']:
                                link_data = {
                                    'session': session_id,
                                    'url': doc_url,
                                    'name': doc_title,
                                }
                                self.storage.set_link(link_data)

                # parsing VOTES
                # TODO check, the condition may stink
                print(f'parse votes {parse_votes} {was_session_in_review} {current_session.is_new}')
                if parse_votes and (was_session_in_review or current_session.is_new):
                    vote_parser = VotesParser(self.storage, current_session)
                    vote_parser.parse_votes(request_session, session_htree)

                # parsing SPEECHES
                print("parse speeches?: ", parse_speeches, parse_all_speeches, parse_new_speeches)
                if parse_speeches and (parse_all_speeches or parse_new_speeches):
                    start_order = 0
                    speech_urls = []
                    for orginal_speech_unid in speech_unids:
                        try:
                            speech_urls.append(self.magnetograms[orginal_speech_unid])
                        except:
                            pass

                    print("speech_unids")
                    print(speech_unids)

                    speech_parser = SpeechParser(self.storage, speech_urls, current_session, start_time)
                    speech_parser.parse(parse_new_speeches)



    def get_session_type(self, type_text):
        type_text = type_text.lower().strip()
        return SESSION_TYPES.get(type_text.lower(), 'unknown')

    def find_date_form_table(self, sklic_tree):
        date_str = None
        time_str = None
        for tr in sklic_tree.cssselect('form>table>tbody>tr'):
            td = tr.cssselect('td')
            try:
                if td[0].cssselect("b")[0].text == 'Datum':
                    span = td[1].cssselect("span")
                    if span:
                        date_str = span[0].text
                    else:
                        date_str = td[1].text
                if td[0].cssselect("b")[0].text == 'Ura':
                    span = td[1].cssselect("span")
                    if span:
                        time_str = span[0].text
                    else:
                        time_str = td[1].text
                    if not re.search("^\d\d:\d\d$", time_str):
                        time_str = None
            except Exception as e:
                print(e)

        if date_str:
            # replace brackets
            date_str = date_str.replace('(', '').replace(')', '')
            if time_str:
                return datetime.strptime(f'{date_str} {time_str}', '%d. %m. %Y %H:%M')
            # TODO send page date falure
            return datetime.strptime(date_str, '%d. %m. %Y')
        # TODO send page date falure
        return None


# Odločitve
"""
parser za govore:
* sparsa govor v pregledu. In nato ko seja ni več v pregledu ga še enktat sparsa. Vse govore seje unvalidira in shrani nove.
* parser za govore se poganja samo 1x na dan ponoči
* shrani si koliko govorov je na seji in doparsaj nove govore.
"""
