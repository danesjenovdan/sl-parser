import requests
import re
import sentry_sdk
from lxml import html, etree
from enum import Enum
from datetime import datetime


class ParserState(Enum):
    META = 0
    PRE_CONTENT = 1
    NAME = 2
    CONTENT = 3
    TRAK = 4


TEST_TRANSCRIPT_URL = 'https://www.dz-rs.si/wps/portal/Home/seje/evidenca/!ut/p/z1/04_Sj9CPykssy0xPLMnMz0vMAfIjo8zivSy9Hb283Q0N3E3dLQwCQ7z9g7w8nAwsPE31w9EUGAWZGgS6GDn5BhsYGwQHG-lHEaPfAAdwNCBOPx4FUfiNL8gNDQ11VFQEAF8pdGQ!/dz/d5/L2dBISEvZ0FBIS9nQSEh/?mandat=VIII&type=sz&uid=E910FA6F117B3BA5C12587DF003D0E15'
TEST_TRANSCRIPT_URL = 'https://www.dz-rs.si/wps/portal/Home/seje/evidenca/!ut/p/z1/04_Sj9CPykssy0xPLMnMz0vMAfIjo8zivSy9Hb283Q0N3E3dLQwCQ7z9g7w8nAwsPE31w9EUGAWZGgS6GDn5BhsYGwQHG-lHEaPfAAdwNCBOPx4FUfiNL8gNDQ11VFQEAF8pdGQ!/dz/d5/L2dBISEvZ0FBIS9nQSEh/?mandat=VIII&type=mag&uid=7AAEE04B11CEB3FFC12587AD00321594'

class SpeechParser(object):
    # regexi
    ANY_SPACES_BETWEEN_B_TAGS = r"</b>(\s*)<b>"
    ANY_EMPTY_B_TAGS = r"<b>(\s*)</b>"
    BR_TAG = r"<br\s*/?>"
    REGEX_IS_START_OF_CONTENT = r'seja .{5,14} (ob)?\s?\d{1,2}'
    REGEX_START_WIERD_WB_SESSION = r'Odprti .{3} seje se je začel ob \d\d'
    FIND_PERSON = r'(^(Nadaljevanje )?[A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ.]{3,25}\s*(?:[(A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ)])*? [A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ. ]{3,25}){1}(\([A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏa-zčšžćöđòóôöüûúùàáäâìíîï ]*\)){0,1}(:)?(\s)?'
    FIND_MISTER_OR_MADAM = r'(^GOSPOD\s?_{4,50}|^GOSPA\s?_{4,50})(:)?'
    FIND_TRAK = r'^([\dOab\.]{1,4}\s*.|[\dOab]{1,4}\s*.\s*(in|-)??\s*[\dOab]{1,4}\s*.)?\s*TRAK\b'
    FIND_SESSION_PAUSE = r'\(Seja .{6,10}(prekinjena|nadaljevala) .{6,10}\)'
    FIND_END_OF_SESSION = r'\(SEJA JE .{3,10} PREKINJENA .{10,35}\)|(^Seja .{5,10} konča)'
    SKIP_SESSION_PAUSE = r'\(Seja je bila prekinjena.{5,15} se je nadaljevala.{5,15}\)'

    TRACK_CONTINUE_WORDS = ['(nadaljevanje)', '(Nadaljevanje)']

    # data
    page_content = []
    meta = []
    current_text = []
    current_person = None
    date_of_sitting = None

    def __init__(self, storage, urls, session_id, session_start_time):
        self.urls = urls
        self.storage = storage
        self.session_id = session_id
        self.session_start_time = session_start_time

    def parse(self, parse_new_speeches=False):
        start_order = 0
        for url in self.urls:
            self.page_content = []
            self.meta = []
            self.current_text = []
            self.current_person = None
            self.date_of_sitting = None
            speeches_content = requests.get(url=url).text
            htree = html.fromstring(speeches_content)

            err_mgs = htree.cssselect('form span.wcmLotusMessage')

            if err_mgs and err_mgs[0].text == 'Podatki dokumenta so nedostopni.':
                print('---_____retry another document ________------')
                return

            self.date_of_sitting = htree.cssselect("table td span")[-1].text

            self.parse_content(htree)

            if parse_new_speeches:
                last_added_index = self.storage.sessions_speech_count.get(self.session_id, 0)
            else:
                last_added_index = None

            print(f'document has {len(self.page_content)} speeches')
            start_order = self.save_speeches(
                start_order,
                last_added_index,
                self.session_start_time,
            )
            # Dont parse next spech page if cureent isn't valid
            if start_order == None:
                break

    # getters
    def get_content(self):
        return self.page_content

    def get_meta_data(self):
        return self.meta

    def get_sitting_date(self):
        return self.date_of_sitting

    # main loop
    def parse_content(self, htree):
        output_text = htree.cssselect(".fieldset span.outputText")[0]
        etree.strip_tags(output_text, 'font')
        output_text_string = self.tostring_unwraped(output_text)
        output_text_string = re.sub(self.ANY_SPACES_BETWEEN_B_TAGS, "\\1", output_text_string, 0, re.MULTILINE)
        output_text_string = re.sub(self.ANY_EMPTY_B_TAGS, "\\1", output_text_string, 0, re.MULTILINE)
        lines = re.split(self.BR_TAG, output_text_string, 0, re.MULTILINE)
        lines = list(map(str.strip, lines))

        self.state = ParserState.META
        self.current_person = None
        self.current_text = []
        for line in lines:
            line_tree = html.fromstring(f'<span>{line}</span>')

            if self.find_trak(line_tree):
                continue

            if self.skip_line_if_needed(line_tree.text_content()):
                continue

            if self.state == ParserState.META:
                self.meta.append(line_tree.text_content())
                if (re.search(self.REGEX_IS_START_OF_CONTENT, line, re.IGNORECASE) or
                    line.startswith('Besedilo je objavljeno') or
                    re.search(self.REGEX_START_WIERD_WB_SESSION, line, re.IGNORECASE)):
                    self.state = ParserState.PRE_CONTENT

            elif self.state == ParserState.NAME:
                self.parse_person_line(line_tree)

            elif self.state == ParserState.CONTENT:
                self.parse_text_line(line_tree)

            elif self.state == ParserState.PRE_CONTENT:
                if not line.strip():
                    continue
                else:
                    self.parse_person_line(line_tree)
            elif self.state == ParserState.TRAK:
                # work on original line (with bold tags)
                temp_line = line
                if not temp_line.strip():
                    continue
                for skip_word in self.TRACK_CONTINUE_WORDS:
                    if temp_line.startswith(skip_word):
                        temp_line = temp_line[len(skip_word):]
                        line_tree = html.fromstring(f'<span>{temp_line}</span>')

                self.parse_person_line(line_tree)


        if self.current_person and self.current_text:
            self.page_content.append({
                'person': self.fix_name(self.current_person),
                'content': '\n'.join(self.current_text)
            })

    def tostring_unwraped(self, element):
        string = element.text or ''
        for child in element.getchildren():
            string += html.tostring(child, encoding='unicode')
        string += element.tail or ''
        return string

    def parse_person_line(self, line_tree):
        name_candidate = line_tree.cssselect('b')
        speaker=None
        if name_candidate:
            name_candidate = name_candidate[0].text

            # check if bolded text is valid person name
            try:
                person_line = re.findall(self.FIND_PERSON, name_candidate)
                mister_or_madam_line = re.findall(self.FIND_MISTER_OR_MADAM, name_candidate)
            except Exception as e:
                person_line = []
                person_line = []
                print('fail find person with "name"', str(person_line))
                sentry_sdk.capture_message(f'Find person regex fails with error {e}. Name candidate is: {name_candidate}')
            if len(person_line) == 1 and self.is_valid_name(person_line[0][0]):
                speaker = person_line[0][0]
            elif len(mister_or_madam_line) == 1:
                speaker = mister_or_madam_line[0][0]

            if speaker:
                if self.current_person and self.current_text:
                    self.page_content.append({
                        'person': self.fix_name(self.current_person),
                        'content': '\n'.join(self.current_text)
                    })
                    self.current_text = []

                self.current_person = speaker
                try:
                    text = line_tree.cssselect('span')[0].getchildren()[0].tail.strip()
                    self.current_text.append(text)
                except:
                    pass
                self.state = ParserState.CONTENT
            else:
                self.parse_text_line(line_tree)
                self.state = ParserState.CONTENT
        else:
            self.parse_text_line(line_tree)
            self.state = ParserState.CONTENT

    def parse_text_line(self, line_tree):
        line = line_tree.text_content()
        if re.findall(self.FIND_SESSION_PAUSE, line):
            return
        if re.findall(self.FIND_END_OF_SESSION, line):
            return

        if not line.strip():
            self.state = ParserState.NAME
        else:
            if self.state == ParserState.TRAK and self.current_text:
                self.append_to_last(line)
            else:
                self.current_text.append(line)

    def find_trak(self, line_tree):
        bold = line_tree.cssselect('b')
        if bold:
            trak_candidat = bold[0].text
            if isinstance(trak_candidat, str):
                if re.search(self.FIND_TRAK, trak_candidat):
                    self.state = ParserState.TRAK
                    return True
        return False

    def append_to_last(self, text):
        while self.current_text and not self.current_text[-1]:
            del self.current_text[-1]
        if self.current_text:
            self.current_text[-1] += text
        else:
            self.current_text.append(text)

    def skip_line_if_needed(self, text):
        if re.search(self.SKIP_SESSION_PAUSE, text):
            return True
        else:
            return False


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
            'prehajamo',
            'dnevnega',
            'poročilo',
            'problematika',
            'evropske',
            'evropsko',
            'administrativne',
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
            'onesnaženost',
            'problematiko',
            'aktualne',
        ]
        for word in forbiden_name_words:
            if word in lower_name:
                return False
        return True

    def fix_name(self, full_name):
        full_name = full_name.strip()
        remove_from_name = [
            'PREDSEDNIK ',
            'PREDSENDIK ',
            'PODPREDSEDNIK ',
            'PODPREDSENIK ',
            'PODPREDSEDNICA ',
            'PREDSEDIK ',
            'POD ',
            'PREDSEDNICA ',
            'PREDSEDUJOČI ',
            'PRESEDNICA ',
            'POPDREDSEDNIK ',
            'PREDSENICA ',
            'PRESEDNIK ',
            'PRESDEDNIK ',
            'REDSEDNIK ',
            'PREDSEDDNICA ',
            'PEDSEDNIK ',
            'PREDEDNIK ',
            'PREDSEDNK ',
            'REDSEDNICA ',
            'PREDSDNIK ',
            'DSEDNIK ',
            'PREDEDNICA ',
            'PREDSENIK ',
            'PREDSENDICA ',
            'PRDSEDNIK ',
            'PREDSEDNCA ',
            'PRDSEDNICA ',
            'PREDSEDNNICA ',
            'PREDSEDNI ',
            'Nadaljevanje',
            'PREDSEDINK ',
            'PODPREDSEDINCA ',
            'PODPRDSEDNICA ',
            'PODPREDSEDICA ',
            'PODPREDSEDNI ',
            'PPREDSEDNIK ',
            'PREDSEDNIKCA ',
            'PODPPREDSEDNIK ',
            'PREDSEDNIKA ',
            'PREEDSEDNIK ',
            'PODPREDSDNICA ',
            'POPREDSEDNICA ',
            'PREDSEDSEDNIK ',
            'PODPREDSENDIK ',
            'PREDSEDNIKI ',
            'PODPRDSEDNIK ',
            'PODPPREDSEDNICA ',
            'PPODPREDSEDNI ',
            'PODPEDSEDNIK ',
            'PODREDSEDNIK ',
            'PODPREDSEDNCA ',
            'PODPREDSENICA ',
            'PODPREDSEDNK ',
            'PODPREDSDNIK ',
            'PODREDSEDNICA ',
            'PODPRESEDNICA ',
            'PREDSEDINCA ',
            'PREDSEDNCIA ',
            'PREDSDEDNIK ',
            'PREDSEDDNIK ',
            'PREDESEDNIK ',
            'PREDSDENIK ',
            'PREDESENIK ',
            'PREDSEDICA ',
            'DPREDSEDNIK ',
            'EDSEDNIK ',
            'PODPREDEDNIK ',
        ]
        for word in remove_from_name:
            if full_name.startswith(word):
                full_name = full_name.replace(word, '').strip()
        return full_name

    # save SPEECHES
    def save_speeches(self, start_order, last_added_index=None, session_start_time=None):
        extract_date_reg = r'\((.*?)\)'

        if self.date_of_sitting:
            date_string = self.date_of_sitting
            try:
                start_time = datetime.strptime(date_string, '%d. %m. %Y')
            except:
                # TODO send error
                start_time = session_start_time
        else:
            date_string = re.findall(extract_date_reg, ' '.join(self.meta))
            if date_string:
                start_time = datetime.strptime(date_string[0], '%d. %B %Y')
            else:
                start_time = session_start_time

        if self.page_content:
            if not self.page_content[0]['content']:
                print('[ERROR] Cannot read session content')
                print(self.page_content)
                # TODO send error
                return None

        speech_objs = []
        for order, speech in enumerate(self.page_content):
            the_order = start_order + order + 1
            person_id, added_person = self.storage.get_or_add_person(
                speech['person'].strip()
            )
            # skip adding speech if has lover order than last_added_index [for sessions in review]
            if last_added_index and order < last_added_index:
                continue

            if not speech['content']:
                print(self.page_content)
                sentry_sdk.capture_message(f'Speech is without content session_id: {self.session_id} person_id: {person_id} the_order: {the_order}')
                continue

            speech_objs.append({
                'speaker': person_id,
                'content': speech['content'],
                'session': self.session_id,
                'order': the_order,
                'start_time': start_time.isoformat()
            })
        self.storage.add_speeches(speech_objs)
        return the_order




if __name__ == '__main__':
    SpeechParser(TEST_TRANSCRIPT_URL)

