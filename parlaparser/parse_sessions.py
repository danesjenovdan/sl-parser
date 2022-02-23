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

from parlaparser.settings import BASE_URL
from parlaparser.utils.methods import get_values


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

        mandate = 'VIII'
        session_url_groups = [
            {
                'url':'https://fotogalerija.dz-rs.si/datoteke/opendata/SDZ.XML',
                'root_key': 'SDZ',
                'file_name': 'SDZ.XML',
                'dz_url': 'https://www.dz-rs.si/wps/portal/Home/seje/izbranaSeja'
            },
            # Disable WB sessions
            # {
            #     'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/SDT.XML',
            #     'root_key': 'SDT',
            #     'file_name': 'SDT.XML',
            #     'dz_url': 'https://www.dz-rs.si/wps/portal/Home/seje/izbranaSejaDt'
            # }
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
            for index, session in enumerate(data[url_group['root_key']]['SEJA']):
                print(session['KARTICA_SEJE']['KARTICA_OZNAKA'])
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

                session_url = f'{url_group["dz_url"]}/?mandat={mandate}&seja={session_name}.%20{session_type_xml}&uid={uid}'

                print(session_url)

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
                    first_speech_date = session_htree.cssselect('form>div>table>tbody>tr>td>div>table a>span')[0].text.replace(' ', '').split('Z')[0].strip()
                    start_time = datetime.strptime(first_speech_date, '%d.%m.%Y')
                    session_in_review = False

                    # check if session has any speech document in review
                    for speech_link in session_htree.cssselect('form>div>table>tbody>tr>td>div>table a>span'):
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

                # TODO get organization for sessions of workong bodies
                if organization_name:
                    organization_id, added_org = self.storage.get_or_add_organization(
                        organization_name,
                        {
                            'name': organization_name,
                            'parser_names': f'{organization_name}',
                        },
                    )
                else:
                    organization_id = self.storage.main_org_id

                # get or add session
                session_data, session_added = self.storage.add_or_get_session({
                    'name': f'{session_name}. {session_type_xml.lower()} seja',
                    'organization': organization_id,
                    'organizations': [organization_id],
                    'classification': self.get_session_type(session_type_xml),
                    'start_time': start_time.isoformat(),
                    'in_review': session_in_review,
                    'needs_editing': session_needs_editing,
                    'gov_id': session_url,
                    'mandate_id': self.storage.mandate_id
                })
                session_id = session_data['id']
                if session_data['start_time'] != start_time.isoformat():
                    # patch session start_time if is changed on dz page
                    self.storage.patch_session(session_id, {'start_time': start_time.isoformat()})

                parse_all_speeches = False
                parse_new_speeches = False

                # session is reviewed, reload speeches
                if not session_in_review and (session_id in self.storage.sessions_in_review):
                    # set session to not in review
                    self.storage.patch_session(session_id, {'in_review': False})

                    # unvalidate speeches
                    self.storage.unvalidate_speeches(session_id)

                    # TODO parse new speeches
                    parse_all_speeches = True

                elif session_in_review and not (session_id in self.storage.sessions_in_review):
                    # set session to not in review
                    self.storage.patch_session(session_id, {'in_review': True})
                    parse_new_speeches = True

                elif session_in_review and (session_id in self.storage.sessions_in_review):
                    parse_new_speeches = True
                elif session_added:
                    parse_all_speeches = True


                if session_added and document_unids:
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

                # TODO check, the condition may stink
                if parse_votes and (session_id in self.storage.sessions_in_review or session_added):
                    ballots = self.parse_votes(request_session, session_htree, session_id)

                print("parse speeches?: ",parse_speeches, parse_all_speeches, parse_new_speeches)
                if parse_speeches and (parse_all_speeches or parse_new_speeches):
                    start_order = 0
                    for orginal_speech_unid in speech_unids:
                        speech_url = self.magnetograms[orginal_speech_unid]
                        print('Speech url: ', speech_url)
                        speeches_content = requests.get(url=speech_url).content
                        htree = html.fromstring(speeches_content)

                        err_mgs = htree.cssselect('form span.wcmLotusMessage')

                        if err_mgs and err_mgs[0].text == 'Podatki dokumenta so nedostopni.':
                            print('---_____retry another document ________------')
                            continue

                        meta, speeches, date_of_sitting = self.parse_speeches(htree)

                        if parse_new_speeches:
                            last_added_index = self.storage.sessions_speech_count.get(session_id, 0)
                        else:
                            last_added_index = None

                        start_order = self.save_speeches(
                            session_id,
                            meta,
                            speeches,
                            start_order,
                            organization_id,
                            last_added_index,
                            session_start_time=start_time,
                            date_of_sitting=date_of_sitting
                        )
                        # Dont parse next spech page if cureent isn't valid
                        if start_order == None:
                            break



    def parse_votes(self, request_session, htree, session_id):
        lines = htree.cssselect('form>div>table>tbody>tr')
        for line in lines:
            columns = line.cssselect('td')
            # if there's not date for vote, skip it
            if not columns[0].cssselect('span') or not columns[0].cssselect('span')[0].text:
                continue
            date = columns[0].cssselect('span')[0].text
            print(date)
            time = columns[1].cssselect('span')[0].text
            if columns[3].cssselect('span'):
                epa = columns[3].cssselect('span')[0].text
            else:
                epa = ''
            url_text = columns[4].cssselect('span')[0].text
            ballots_url = columns[4].cssselect('a')[0].get('href')
            uid = parse.parse_qs(parse.urlsplit(ballots_url).query)['uid'][0]


            if self.storage.check_if_motion_is_parsed({'gov_id': uid}):
                print('this vote is already parsed')
                continue

            parsed_ballots = self.parse_ballots(ballots_url)

            try:
                start_time = datetime.strptime(f'{date} {time}', '%d. %m. %Y %X')
            except Exception as e:
                # TODO send sentry error
                print('parse date error', e)
                continue

            motion_meta = parsed_ballots['meta']
            if motion_meta['title']:
                title = f'{motion_meta["title"]} - {motion_meta["doc_name"]}'
            else:
                title = motion_meta["doc_name"]

            # dont parse motion without title
            if not title:
                continue

            legislation_id = None
            if epa:
                if epa in self.storage.legislation.keys():
                    legislation_id = self.storage.legislation[epa]['id']
                else:
                    legislation = self.storage.set_legislation({
                        'epa': epa
                    })
                    legislation_id = legislation['id']

            motion = {
                'title': title,
                'text': title,
                'datetime': start_time.isoformat(),
                'session': session_id,
                'gov_id': uid
            }
            if legislation_id:
                motion['law'] = legislation_id
            vote = {
                'name': title,
                'timestamp': start_time.isoformat(),
                'session': session_id,
            }
            motion_obj = self.storage.set_motion(motion)
            try:
                motion_id = motion_obj['id']
            except:
                # skip adding vote because adding motion was fail
                continue
            vote['motion'] = motion_id
            vote_obj = self.storage.set_vote(vote)
            vote_id = int(vote_obj['id'])

            self.save_balltos(parsed_ballots['ballots'], vote_id)

            # TODO add links to votes...
            # for link in data['links']:
            #     # save links
            #     link_data = {
            #         'motion': motion_id,
            #         #'agenda_item': self.agenda_item_id,
            #         'url': link['url'],
            #         'name': link['title'],
            #         'tags': [link['tag']]
            #     }
            #     if 'law' in motion.keys():
            #         link_data.update({'law': motion['law']})
            #     self.storage.set_link(link_data)

        # follow pagination
        try:
            paging_meta = htree.cssselect(".pagerDeluxe_text")[0].text.split(' ')
        except:
            # This exit method if session has not votes
            return
        current_page = paging_meta[1]
        last_page = paging_meta[3]
        if int(current_page) < int(last_page):
            post_url = htree.cssselect('form')[0].get('action')
            form_id = htree.cssselect('form')[0].get('id')
            view_state = htree.cssselect('input[name="javax.faces.ViewState"]')[0].get('value')
            url_encode = htree.cssselect('input[name="javax.faces.encodedURL"]')[0].get('value')

            url = f'{BASE_URL}{post_url}'
            payload = {
                'vax.faces.encodedURL': url_encode,
                f'{form_id}_SUBMIT': 1,
                f'{form_id}:tableEx1:goto1__pagerGoText': 2,
                'javax.faces.ViewState': view_state,
                f'{form_id}:tableEx1:deluxe1__pagerNext.x': 0,
                f'{form_id}:tableEx1:deluxe1__pagerNext.y': 0,
            }

            response = request_session.post(url, data=payload)
            session_htree = html.fromstring(response.content)
            self.parse_votes(request_session, session_htree, session_id)



    def parse_ballots(self, url):
        output = {
            'ballots': [],
            'meta': {}
        }
        ballots_content = requests.get(url=f'{BASE_URL}{url}').content
        htree = html.fromstring(ballots_content)
        body = htree.cssselect('.stControlBody')[0]
        tables = body.cssselect('table')
        header = tables[0]
        content = tables[1]
        title = ''
        document_name = ''
        # parse header
        for tr in header.cssselect('tbody>tr'):
            tds = tr.cssselect('td')
            span_b = tds[0].cssselect('span>b')
            if not span_b:
                continue
            key = span_b[0].text
            value = tds[1]
            if key == 'Dokument':
                span = value.cssselect('span')
                if not span:
                    continue
                document_name = span[0].text
            if key == 'Naslov':
                em = value.cssselect('span>em')
                if not em:
                    continue
                title = em[0].text
        output['meta'] = {
            'title': title,
            'doc_name': document_name,
        }

        # parse content
        for tr in content.cssselect('tr')[1:]:
            tds = tr.cssselect('td')
            output['ballots'].append({
                'voter': tds[0].text,
                'kvorum': tds[1].text,
                'option': tds[2].text,
            })

        return output

    def save_balltos(self, ballots, vote_id):
        ballots_for_save = []
        for ballot in ballots:
            person_id, added_person = self.storage.get_or_add_person(
                ballot['voter']
            )
            person_option = ''
            kvorum = ballot['kvorum']
            option = ballot['option']
            if not kvorum:
                person_option = 'absent'
            elif option == 'Ni':
                person_option = 'abstain'
            elif option == 'Proti':
                person_option = 'against'
            elif option == 'Za':
                person_option = 'for'
            else:
                raise Exception('Unkonwn option')
            ballots_for_save.append({
                'personvoter': person_id,
                'option': person_option,
                'vote': vote_id
            })
        self.storage.set_ballots(ballots_for_save)



    def parse_speeches(self, htree):
        print('parsing speeches')
        state = ParserState.META
        speaker = None
        content = []
        result = []
        meta = []

        # TODO make method parse_name + tests
        find_person = r'(^(Nadaljevanje )?[A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ.]{3,25}\s*(?:[(A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ)])*? [A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ. ]{3,25}){1}(\([A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏa-zčšžćöđòóôöüûúùàáäâìíîï ]*\)){0,1}(:)?(\s)?'
        find_mister_or_madam = r'(^GOSPOD\s?_{4,50}|^GOSPA\s?_{4,50})(:)?'

        regex_is_start_of_content = r'seja .{5,14} (ob)?\s?\d{1,2}'

        regex_start_wierd_wb_session = r'Odprti .{3} seje se je začel ob \d\d'

        #find_trak_r = r'^([\dOa]{1,4}\s*.)?\s*TRAK\b'
        find_trak_r = r'^([\dOab\.]{1,4}\s*.|[\dOab]{1,4}\s*.\s*(in|-)??\s*[\dOab]{1,4}\s*.)?\s*TRAK\b'

        date_of_sitting = htree.cssselect("table td span")[-1].text

        trak_on_action = False
        append_text_to_last_content = False

        for element in htree.cssselect("span.outputText font, span.outputText br"):
            #line = element.text.strip()
            if element.tag == 'br':
                content.append('\n')
                continue
            # line = ' '.join(map(str.strip, element.xpath("./text()")))
            line = ''.join(element.xpath("./text()"))
            if line == None:
                continue

            # skip line if contians TRAK:
            if re.search(find_trak_r, line):
                trak_on_action = True
                continue

            # resolve track clutter from text
            if trak_on_action:
                track_continue_words = ['(nadaljevanje)', '(Nadaljevanje)']
                for skip_word in track_continue_words:
                    if line.startswith(skip_word):
                        line = line[len(skip_word):].strip()

                # apeend this pharagraph to previous
                append_text_to_last_content = True

                trak_on_action = False

            if state == ParserState.META:
                if line:
                    meta.append(line)

                if re.search(regex_is_start_of_content, line, re.IGNORECASE) or line.startswith('Besedilo je objavljeno') or re.search(regex_start_wierd_wb_session, line, re.IGNORECASE):
                    state = ParserState.CONTENT
            elif state == ParserState.CONTENT:
                if element.getparent().tag == 'b':
                    person_line = re.findall(find_person, line)
                    mister_or_madam_line = re.findall(find_mister_or_madam, line)
                    if len(person_line) == 1 and self.is_valid_name(person_line[0][0]):
                        if speaker:
                            result.append((speaker, ''.join(content)))
                            content = []
                        speaker = person_line[0]
                        append_text_to_last_content = False
                    elif len(mister_or_madam_line) == 1:
                        if speaker:
                            result.append((speaker, ''.join(content)))
                            content = []
                        speaker = mister_or_madam_line[0]
                        append_text_to_last_content = False
                    else:
                        if line.lower().startswith('seja se je kon'):
                            continue

                        # if TRAK is on paragraph then "dont append" new line
                        if append_text_to_last_content:
                            if content:
                                content[-1] += f' {line}'
                            else:
                                content.append(line)
                            append_text_to_last_content = False
                        else:
                            content.append(line)
                else:
                    # skip lines before speeches
                    if not speaker:
                        continue
                    # merge content of TRAK-s
                    if append_text_to_last_content:
                        if content:
                            content[-1] += f' {line}'
                        else:
                            content.append(line)
                        append_text_to_last_content = False
                    else:
                        content.append(line)

        result.append((speaker, ''.join(content)))

        return meta, result, date_of_sitting

    def save_speeches(self, session_id, meta, speeches, start_order, organization_id, last_added_index=None, session_start_time=None, date_of_sitting=None):
        extract_date_reg = r'\((.*?)\)'

        print('organization_id', organization_id)

        if date_of_sitting:
            date_string = date_of_sitting
            try:
                start_time = datetime.strptime(date_string, '%d. %m. %Y')
            except:
                # TODO send error
                start_time = session_start_time
        else:
            date_string = re.findall(extract_date_reg, ' '.join(meta))
            if date_string:
                start_time = datetime.strptime(date_string[0], '%d. %B %Y')
            else:
                start_time = session_start_time

        if speeches:
            if not speeches[0][0]:
                print('[ERROR] Cannot read session content')
                print(speeches)
                # TODO send error
                return None


        speech_objs = []
        for order, (speaker_name, speech) in enumerate(speeches):
            the_order = start_order + order + 1
            person_id, added_person = self.storage.get_or_add_person(
                self.fix_name(speaker_name[0].strip()).strip()
            )
            # skip adding speech if has lover order than last_added_index [for sessions in review]
            if last_added_index and order < last_added_index:
                continue

            if not speech:
                print(speeches)
                sentry_sdk.capture_message(f'Speech is without content session_id: {session_id} person_id: {person_id} the_order: {the_order}')
                continue

            speech_objs.append({
                'speaker': person_id,
                'content': speech,
                'session': session_id,
                'order': the_order,
                'start_time': start_time.isoformat()
            })
        self.storage.add_speeches(speech_objs)
        return the_order

    def fix_name(self, full_name):
        full_name = full_name.strip()
        remove_from_name = [
            'PREDSEDNIK',
            'PREDSENDIK',
            'PODPREDSEDNIK',
            'PODPREDSENIK',
            'PODPREDSEDNICA',
            'PREDSEDIK',
            'POD',
            'PREDSEDNICA',
            'PREDSEDUJOČI',
            'PRESEDNICA',
            'POPDREDSEDNIK',
            'PREDSENICA',
            'PRESEDNIK',
            'PRESDEDNIK',
            'REDSEDNIK',
            'PREDSEDDNICA',
            'PEDSEDNIK',
            'PREDEDNIK',
            'PREDSEDNK',
            'REDSEDNICA',
            'PREDSDNIK',
            'DSEDNIK',
            'PREDEDNICA',
            'PREDSENIK',
            'PREDSENDICA',
            'PRDSEDNIK',
            'PREDSEDNCA',
            'PRDSEDNICA'
            'PREDSEDNNICA',
            'PREDSEDNI',
            'Nadaljevanje',
            'PREDSEDINK',
            'PODPREDSEDINCA',
            'PODPRDSEDNICA',
            'PODPREDSEDICA',
            'PODPREDSEDNI',
            'PPREDSEDNIK',
            'PREDSEDNIKCA',
            'PODPPREDSEDNIK',
            'PREDSEDNIKA',
            'PREEDSEDNIK',
            'PODPREDSDNICA',
            'POPREDSEDNICA',
            'PREDSEDSEDNIK',
            'PODPREDSENDIK',
            'PREDSEDNIKI',
            'PODPRDSEDNIK',
            'PODPPREDSEDNICA',
            'PPODPREDSEDNI',
            'PODPEDSEDNIK',
            'PODREDSEDNIK',
            'PODPREDSEDNCA',
            'PODPREDSENICA',
            'PODPREDSEDNK',
            'PODPREDSDNIK',
            'PODREDSEDNICA',
            'PODPRESEDNICA',
            'PREDSEDINCA',
            'PREDSEDNCIA',
            'PREDSDEDNIK',
            'PREDSEDDNIK',
            'PREDESEDNIK',
            'PREDSDENIK',
            'PREDESENIK',
            'PREDSEDICA',
            'DPREDSEDNIK',
            'EDSEDNIK',
            'PODPREDEDNIK',
        ]
        for word in remove_from_name:
            word = word + ' '
            if full_name.startswith(word):
                full_name = full_name.replace(word, '').strip()
        return full_name

    def is_valid_name(self, full_name):
        """
        Checker for valid names
        Name is unvalid if;
            * if combiend form more 5 words
            * contains forbiden words
        """
        full_name = full_name.strip()
        if len(full_name.split(' ')) > 5:
            return False
        lower_name = full_name.lower()
        forbiden_name_words = [
            'obravnav',
            'postopka',
            'zakona',
            'prekinjena',
            'vprašanja',
            'davku',
            'prehajamo'
            'dnevnega',
            'poročilo',
            'problematika',
            'evropske',
            'administrativne'
            'predstavitev',
            'industrijski',
            'nalezljivih',
            'predlogu',
            'skupno',
            'obvestilo',
            'omenjene',
            'gospodarstvu',
            'neonacizem',
            'negospodarnega',
            'nadzor',
            'sodišča',
            'prisilni',
            'slovenije',
            'madžarkskega',
            'predlog',
            'dogovor',
            'proračuna',
            'nadaljevanje',
        ]
        for word in forbiden_name_words:
            if word in lower_name:
                return False
        return True

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
                    date_str = td[1].cssselect("span")[0].text
                if td[0].cssselect("b")[0].text == 'Ura':
                    time_str = td[1].cssselect("span")[0].text
                    if not re.search("^\d\d:\d\d$", time_str):
                        time_str = None
            except:
                pass

        if date_str:
            if time_str:
                return datetime.strptime(f'{date_str} {time_str}', '%d. %m. %Y %H:%M')
            # TODO send page date falure
            return datetime.strptime(date_str, '%d. %m. %Y')
        # TODO send page date falure
        return None


# perser imen regex

# BRANKO SIMONOVIČ (PS DeSUS):
# PODPREDSEDNICA TINA HEFERLE:
# PREDSEDNIK MAG. DEJAN ŽIDAN:


# ([A-ZČŠŽĆĐ. ]{5,50}){1}(\([A-Za-zđčćžšČĆŽŠŽĐ ]*\)){0,1}(:)?

# ([A-ZČŠŽĆĐ. ]{5,50}){1}  <--- poslanec

# (\([A-Za-zđčćžšČĆŽŠŽĐ ]*\)){0,1}  <-- stranka

# (:)? <--- opcijsko dvopičje


# Odločitve
"""
parser za govore:
* sparsa govor v pregledu. In nato ko seja ni več v pregledu ga še enktat sparsa. Vse govore seje unvalidira in shrani nove.
* parser za govore se poganja samo 1x na dan ponoči
* shrani si koliko govorov je na seji in doparsaj nove govore.
"""
