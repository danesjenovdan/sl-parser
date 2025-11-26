import re
from datetime import datetime
from enum import Enum

import requests
import sentry_sdk
from lxml import etree, html


class ParserState(Enum):
    META = 0
    PRE_CONTENT = 1
    NAME = 2
    CONTENT = 3
    TRAK = 4


TEST_TRANSCRIPT_URL = "https://www.dz-rs.si/wps/portal/Home/seje/evidenca/!ut/p/z1/04_Sj9CPykssy0xPLMnMz0vMAfIjo8zivSy9Hb283Q0N3E3dLQwCQ7z9g7w8nAwsPE31w9EUGAWZGgS6GDn5BhsYGwQHG-lHEaPfAAdwNCBOPx4FUfiNL8gNDQ11VFQEAF8pdGQ!/dz/d5/L2dBISEvZ0FBIS9nQSEh/?mandat=VIII&type=sz&uid=E910FA6F117B3BA5C12587DF003D0E15"
TEST_TRANSCRIPT_URL = "https://www.dz-rs.si/wps/portal/Home/seje/evidenca/!ut/p/z1/04_Sj9CPykssy0xPLMnMz0vMAfIjo8zivSy9Hb283Q0N3E3dLQwCQ7z9g7w8nAwsPE31w9EUGAWZGgS6GDn5BhsYGwQHG-lHEaPfAAdwNCBOPx4FUfiNL8gNDQ11VFQEAF8pdGQ!/dz/d5/L2dBISEvZ0FBIS9nQSEh/?mandat=VIII&type=mag&uid=7AAEE04B11CEB3FFC12587AD00321594"


class SpeechParser(object):
    # regexi
    ANY_SPACES_BETWEEN_B_TAGS = r"</b>(\s*)<b>"
    ANY_EMPTY_B_TAGS = r"<b>(\s*)</b>"
    BR_TAG = r"<br\s*/?>"
    REGEX_IS_START_OF_CONTENT = r"seja .{5,14} (ob)?\s?\d{1,2}"
    REGEX_START_WIERD_WB_SESSION = r"Odprti .{3} seje se je začel ob \d\d"
    FIND_PERSON = r"(^(Nadaljevanje |nadaljevanje )?[A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ.]{3,25}\s*(?:[(A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ)])*? [A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ. ]{3,25}){1}(\([A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏa-zčšžćöđòóôöüûúùàáäâìíîï ]*\)){0,1}(:)?(\s)?"
    FIND_MISTER_OR_MADAM = r"(^GOSPOD\s?_{4,50}|^GOSPA\s?_{4,50})(:)?"
    FIND_MINISTER = r"(^(Nadaljevanje |nadaljevanje )?[A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ.]{3,25}\s*(?:[(a-zčšžćöđòóôöüûúùàáäâìíîï,)])*? [A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏ., ]{3,25}){1}(\([A-ZČŠŽĆÖĐÒÓÔÖÜÛÚÙÀÁÄÂÌÍÎÏa-zčšžćöđòóôöüûúùàáäâìíî,ï ]*\)){0,1}(:)?(\s)?"
    FIND_TRAK = r"^([\dOab\.]{1,4}\s*.|[\dOab]{1,4}\s*.\s*(in|-)??\s*[\dOab]{1,4}\s*.)?\s*TRAK\b"
    FIND_SESSION_PAUSE = r"\(Seja .{6,10}(prekinjena|nadaljevala) .{6,10}\)"
    FIND_END_OF_SESSION = (
        r"\(SEJA JE .{3,10} PREKINJENA .{10,35}\)|(^Seja .{5,10} konča)"
    )
    SKIP_SESSION_PAUSE = r"\(Seja je bila prekinjena.{5,15} se je nadaljevala.{5,15}\)"

    START_AT_REGEX = r"(?:pri|za)č[ea]la?\s+(?:ob\s*)?(\d{1,2})[.:]\s*(?:(\d{2})|uri|0)"

    TRACK_CONTINUE_WORDS = ["(nadaljevanje)", "(Nadaljevanje)"]

    DATE_REGEX = r"\d{1,2}\.\s*\d{1,2}\.\s*\d{4}"

    START_DATE_REGEX = r"\((\d{1,2}\.\s*(januar|februar|marec|april|maj|junij|julij|avgust|september|oktober|november|december)\s+\d{4})\)"

    DEBUG = False

    # data
    page_content = []
    meta = []
    current_text = []
    current_person = None
    date_of_sitting = None

    def __init__(self, storage, urls, session, start_date, debug=False):
        self.urls = urls
        self.storage = storage
        self.session = session
        self.start_date = start_date
        self.session_start_time = None
        self.page_htmls = []
        self.pages = []
        self.titles = []
        self.page_in_review = []
        self.DEBUG = debug
        self.read_files()
        self.in_review_controller()

    def read_files(self):
        for url in self.urls:
            print(f"Opening speeches from url: {url}")
            speeches_content = requests.get(url=url).text
            htree = html.fromstring(speeches_content)
            self.page_htmls.append({"url": url, "tree": htree})
            title = self.parse_title(htree)
            self.titles.append(title)
            if "v pregled" in title.lower():
                self.page_in_review.append(True)
            else:
                self.page_in_review.append(False)

    def in_review_controller(self):
        self.parse_all_speeches = False
        self.parse_new_speeches = False
        was_session_in_review = self.storage.session_storage.is_session_in_review(
            self.session
        )
        session_in_review = any(self.page_in_review)
        if not session_in_review and was_session_in_review:
            # set session to not in review
            if self.session.in_review:
                self.session.patch_session({"in_review": False})
            # unvalidate speeches
            self.session.unvalidate_speeches()

            # TODO parse new speeches
            self.parse_all_speeches = True
        elif session_in_review and not was_session_in_review:
            # set session to not in review
            self.parse_new_speeches = True

        elif session_in_review and was_session_in_review:
            self.parse_new_speeches = True
        elif self.session.is_new:
            self.parse_all_speeches = True
        else:
            speech_count = self.session.get_speech_count()
            if speech_count == 0:
                if not self.session.in_review:
                    self.session.patch_session({"in_review": True})
                self.parse_all_speeches = True

    def update_session_start_time(self, time):
        """set session start time if not set yet"""
        if not self.session.start_time:
            start_date = None
            if self.page_htmls:
                htree = self.page_htmls[0]["tree"]
                # gat date of sitting: '6. 10. 2025'
                maybe_date_element = htree.cssselect("table td")
                if maybe_date_element:
                    start_date = maybe_date_element[-1].text
                else:
                    maybe_date_element = htree.cssselect("form>div>div")
                    if maybe_date_element:
                        maybe_date = " ".join(
                            [self.tostring_unwraped(i) for i in maybe_date_element]
                        )
                        dates = re.findall(self.DATE_REGEX, maybe_date)
                        if dates:
                            start_date = dates[0]

            if start_date:
                new_start = datetime.strptime(start_date, "%d. %m. %Y")
            else:
                new_start = self.get_start_sitting_from_meta()
            if new_start:
                print("SET SESSION START TIME", new_start, time)
                self.session.update_start_time(new_start)

        start_time = datetime.strptime(
            self.session.start_time, "%Y-%m-%dT%H:%M:%S"
        )  # from isoformat
        # check if start_time is set in the middle of the night
        if self.is_midnight(start_time):
            try:
                hour, minute = time.split(":")
                start_time = start_time.replace(hour=int(hour), minute=int(minute))
                print("SET SESSION START TIME MIDNIGHT", new_start, time)
                self.session.update_start_time(start_time)
            except Exception as e:
                print(e)
                pass

    def parse(self):
        if not (self.parse_all_speeches or self.parse_new_speeches):
            print("No need to parse speeches")
            return
        start_order = 0
        for idx, page in enumerate(self.page_htmls):
            print(f"Parsing speeches from url: {page['url']}")
            htree = page["tree"]
            self.page_idx = idx
            self.page_content = []
            self.meta = []
            self.current_text = []
            self.current_person = None
            self.date_of_sitting = None

            err_mgs = htree.cssselect("form span.wcmLotusMessage")

            if err_mgs and err_mgs[0].text == "Podatki dokumenta so nedostopni.":
                print("---_____retry another document ________------")
                return

            # gat date of sitting
            maybe_date_element = htree.cssselect("table td")
            if maybe_date_element:
                self.date_of_sitting = maybe_date_element[-1].text
            else:
                maybe_date_element = htree.cssselect("form>div>div")
                if maybe_date_element:
                    maybe_date = " ".join(
                        [self.tostring_unwraped(i) for i in maybe_date_element]
                    )
                    dates = re.findall(self.DATE_REGEX, maybe_date)
                    if dates:
                        self.date_of_sitting = dates[0]

            title = self.parse_title(htree)
            self.titles.append(title)
            if "v pregled" in title.lower():
                self.page_in_review.append(True)
            else:
                self.page_in_review.append(False)

            self.parse_content(htree)

            if self.parse_new_speeches:
                last_added_index = self.session.get_speech_count()
                print(f"Session has {last_added_index} speeches")
            else:
                last_added_index = None

            print(f"document has {len(self.page_content)} speeches")
            if not self.DEBUG:
                start_order = self.save_speeches(
                    start_order,
                    last_added_index,
                    self.session.start_time,
                )
            # Dont parse next spech page if cureent isn't valid
            if start_order == None:
                break

    # getters
    def get_content(self):
        return self.page_content

    def is_in_review(self):
        return any(self.page_in_review)

    def get_meta_data(self):
        return self.meta

    def get_sitting_date(self):
        return self.date_of_sitting

    def parse_title(self, htree):
        title = ""
        try:
            title = htree.cssselect("form>h1")[0].text
        except:
            pass
        return title

    def get_start_sitting_from_meta(self):
        months = [
            "januar",
            "februar",
            "marec",
            "april",
            "maj",
            "junij",
            "julij",
            "avgust",
            "september",
            "oktober",
            "november",
            "december",
        ]
        date_search = re.search(self.START_DATE_REGEX, " ".join(self.meta))
        if date_search:
            try:
                date_string = date_search.groups()[0]
                day, month, year = date_string.strip().split(" ")
                return datetime(int(day.strip(".")), months.index(month) + 1, int(year))
            except Exception as e:
                print("get_start_sitting_from_meta", e)
        return None

    # main loop
    def parse_content(self, htree):
        # output_text = htree.cssselect(".fieldset span.outputText")[0]
        try:
            # output_text = htree.cssselect("form > div.fieldset")[0]
            output_text = htree.cssselect("form > div")[1]
        except:
            return
        etree.strip_tags(output_text, "font")
        output_text_string = self.tostring_unwraped(output_text)
        output_text_string = re.sub(
            self.ANY_SPACES_BETWEEN_B_TAGS, "\\1", output_text_string, 0, re.MULTILINE
        )
        output_text_string = re.sub(
            self.ANY_EMPTY_B_TAGS, "\\1", output_text_string, 0, re.MULTILINE
        )
        lines = re.split(self.BR_TAG, output_text_string, 0, re.MULTILINE)
        lines = list(map(str.strip, lines))
        if self.DEBUG:
            lines = lines[:150]

        self.state = ParserState.META
        self.current_person = None
        self.current_text = []

        for line in lines:
            line_tree = html.fromstring(f"<span>{line}</span>")

            if self.DEBUG:
                print("---")
                print(self.state)
                print(line)
                print(line_tree)
                print(line_tree.text_content())

            if self.find_trak(line_tree):
                continue

            if self.skip_line_if_needed(line_tree.text_content()):
                continue

            if self.state == ParserState.META:
                self.meta.append(line_tree.text_content())
                if (
                    re.search(self.REGEX_IS_START_OF_CONTENT, line, re.IGNORECASE)
                    or line.startswith("Besedilo je objavljeno")
                    or re.search(self.REGEX_START_WIERD_WB_SESSION, line, re.IGNORECASE)
                ):
                    self.state = ParserState.PRE_CONTENT
                    if self.page_idx == 0:
                        time = self.get_time_from_line(line)
                        print(time)
                        if time:
                            self.update_session_start_time(time)

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
                        temp_line = temp_line[len(skip_word) :]
                        line_tree = html.fromstring(f"<span>{temp_line}</span>")

                self.parse_person_line(line_tree)

        if self.current_person and self.current_text:
            self.page_content.append(
                {
                    "person": self.fix_name(self.current_person),
                    "content": "\n".join(self.current_text).lstrip(":"),
                }
            )

        # prevent to adding speeches form two equals documents
        if self.page_content in self.pages:
            self.page_content = []
        else:
            self.pages.append(self.page_content)

    def tostring_unwraped(self, element):
        string = element.text or ""
        for child in element.getchildren():
            string += html.tostring(child, encoding="unicode")
        string += element.tail or ""
        return string

    def parse_person_line(self, line_tree):
        """
        try to find person name in line if not found parse line as text
        """
        line = line_tree.text_content()
        if not line.strip():
            self.state = ParserState.NAME
            return
        name_candidate = line_tree.cssselect("b")
        speaker = None
        if name_candidate:
            if self.DEBUG:
                print(f"Found bolded text: {name_candidate[0].text.strip()}")
            # check if bolded text is valid person name
            try:
                name_candidate = name_candidate[0].text.strip()
                person_line = re.findall(self.FIND_PERSON, name_candidate)
                mister_or_madam_line = re.findall(
                    self.FIND_MISTER_OR_MADAM, name_candidate
                )
                minister_line = re.findall(self.FIND_MINISTER, name_candidate)
            except Exception as e:
                person_line = []
                mister_or_madam_line = []
                minister_line = []
                print('fail find person with "name"', str(person_line))
                sentry_sdk.capture_message(
                    f"Find person regex fails with error {e}. Name candidate is: {name_candidate}"
                )
            if len(person_line) == 1 and self.is_valid_name(person_line[0][0]):
                speaker = person_line[0][0]
            elif len(mister_or_madam_line) == 1:
                speaker = mister_or_madam_line[0][0]
            elif len(minister_line) == 1 and self.is_valid_name(minister_line[0][0]):
                speaker = minister_line[0][0]

            if speaker:
                if self.DEBUG:
                    print(f"Found speaker: {speaker}")
                if self.current_person and self.current_text:
                    self.page_content.append(
                        {
                            "person": self.fix_name(self.current_person),
                            "content": "\n".join(self.current_text).lstrip(":"),
                        }
                    )
                    self.current_text = []

                self.current_person = speaker
                try:
                    text = line_tree.cssselect("span")[0].getchildren()[0].tail.strip()
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
        bold = line_tree.cssselect("b")
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
        if len(full_name.split(" ")) > 5:
            return False
        lower_name = full_name.lower()
        forbiden_name_words = [
            "obravnav",
            "postopka",
            "zakona",
            "prekinjena",
            "vprašanja",
            "davku",
            "prehajamo",
            "dnevnega",
            "poročilo",
            "problematika",
            "evropske",
            "evropsko",
            "administrativne",
            "predstavitev",
            "industrijski",
            "nalezljivih",
            "predlogu",
            "skupno",
            "obvestilo",
            "omenjene",
            "gospodarstvu",
            "neonacizem",
            "negospodarnega",
            "nadzor",
            "sodišča",
            "prisilni",
            "slovenije",
            "madžarkskega",
            "predlog",
            "dogovor",
            "proračuna",
            "onesnaženost",
            "problematiko",
            "aktualne",
            "zakonsko",
            "predkazenskih",
            "postopkov",
            "zoper",
            "seznanitev",
        ]
        for word in forbiden_name_words:
            if word in lower_name:
                return False
        return True

    def fix_name(self, full_name):
        full_name = full_name.strip()
        remove_from_name = [
            "PREDSEDNIK ",
            "PREDSENDIK ",
            "PODPREDSEDNIK ",
            "PODPREDSENIK ",
            "PODPREDSEDNICA ",
            "PREDSEDIK ",
            "POD ",
            "PREDSEDNICA ",
            "PREDSEDUJOČI ",
            "PRESEDNICA ",
            "POPDREDSEDNIK ",
            "PREDSENICA ",
            "PRESEDNIK ",
            "PRESDEDNIK ",
            "REDSEDNIK ",
            "PREDSEDDNICA ",
            "PEDSEDNIK ",
            "PREDEDNIK ",
            "PREDSEDNK ",
            "REDSEDNICA ",
            "PREDSDNIK ",
            "DSEDNIK ",
            "PREDEDNICA ",
            "PREDSENIK ",
            "PREDSENDICA ",
            "PRDSEDNIK ",
            "PREDSEDNCA ",
            "PRDSEDNICA ",
            "PREDSEDNNICA ",
            "PREDSEDNI ",
            "Nadaljevanje",
            "nadaljevanje",
            "PREDSEDINK ",
            "PODPREDSEDINCA ",
            "PODPRDSEDNICA ",
            "PODPREDSEDICA ",
            "PODPREDSEDNI ",
            "PPREDSEDNIK ",
            "PREDSEDNIKCA ",
            "PODPPREDSEDNIK ",
            "PREDSEDNIKA ",
            "PREEDSEDNIK ",
            "PODPREDSDNICA ",
            "POPREDSEDNICA ",
            "PREDSEDSEDNIK ",
            "PODPREDSENDIK ",
            "PREDSEDNIKI ",
            "PODPRDSEDNIK ",
            "PODPPREDSEDNICA ",
            "PPODPREDSEDNI ",
            "PODPEDSEDNIK ",
            "PODREDSEDNIK ",
            "PODPREDSEDNCA ",
            "PODPREDSENICA ",
            "PODPREDSEDNK ",
            "PODPREDSDNIK ",
            "PODREDSEDNICA ",
            "PODPRESEDNICA ",
            "PREDSEDINCA ",
            "PREDSEDNCIA ",
            "PREDSDEDNIK ",
            "PREDSEDDNIK ",
            "PREDESEDNIK ",
            "PREDSDENIK ",
            "PREDESENIK ",
            "PREDSEDICA ",
            "DPREDSEDNIK ",
            "EDSEDNIK ",
            "PODPREDEDNIK ",
        ]
        for word in remove_from_name:
            if full_name.startswith(word):
                full_name = full_name.replace(word, "").strip()
        return full_name

    # save SPEECHES
    def save_speeches(
        self, start_order, last_added_index=None, session_start_time=None
    ):
        extract_date_reg = r"\((.*?)\)"
        the_order = start_order

        if self.date_of_sitting:
            date_string = self.date_of_sitting
            try:
                start_time = datetime.strptime(date_string, "%d. %m. %Y")
            except:
                # TODO send error
                start_time = session_start_time
        else:
            date_string = re.findall(extract_date_reg, " ".join(self.meta))
            if date_string:
                start_time = datetime.strptime(date_string[0], "%d. %B %Y")
            else:
                start_time = session_start_time

        if self.page_content:
            if not self.page_content[0]["content"]:
                print("[ERROR] Cannot read session content")
                print(self.page_content)
                # TODO send error
                return None

        speech_objs = []
        skipped_speeches = 0
        for order, speech in enumerate(self.page_content):
            the_order = start_order + order + 1
            person = self.storage.people_storage.get_or_add_object(
                {"name": speech["person"].strip()}
            )

            # skip adding speech if has lover and equal order than last_added_index [for sessions in review]
            if last_added_index and the_order <= last_added_index:
                if self.DEBUG:
                    print("This speech is already parsed")
                skipped_speeches += 1
                continue

            if not speech["content"]:
                print(self.page_content)
                sentry_sdk.capture_message(
                    f"Speech is without content session_id: {self.session.id} person_id: {person.id} the_order: {the_order}"
                )
                continue

            if isinstance(start_time, str):
                pass
            else:
                start_time = start_time.isoformat()

            speech_objs.append(
                {
                    "speaker": person.id,
                    "content": speech["content"],
                    "session": self.session.id,
                    "order": the_order,
                    "start_time": start_time,
                }
            )
        self.session.add_speeches(speech_objs)
        print(f"Added speeches: {len(speech_objs)}")
        print(f"Skipped speeches: {skipped_speeches}")
        return the_order

    def get_time_from_match(self, match):
        hour, minute = match.group(1, 2)
        if minute is None:
            minute = "00"
        return f"{hour}:{minute}"

    def get_time_from_line(self, line):
        match = re.search(self.START_AT_REGEX, line, re.IGNORECASE)
        if match:
            return self.get_time_from_match(match)

    def is_midnight(self, dt):
        return (dt.hour, dt.minute, dt.second, dt.microsecond) == (0, 0, 0, 0)


if __name__ == "__main__":
    speech_parser = SpeechParser(None, [TEST_TRANSCRIPT_URL], None, None, debug=True)
