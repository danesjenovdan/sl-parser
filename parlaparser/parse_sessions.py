import locale
import re
from datetime import datetime
from enum import Enum

import requests
import sentry_sdk
import xmltodict
from lxml import html
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

from parlaparser.parse_speeches import SpeechParser
from parlaparser.parse_votes import VotesParser
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
    "redna": "regular",
    "izredna": "irregular",
    "nujna": "urgent",
}


class SessionParser(object):
    def __init__(self, storage):
        self.storage = storage
        locale.setlocale(locale.LC_TIME, "sl_SI.utf-8")
        self.documents = {}
        self.magnetograms = {}

    def load_documents(self, data, root_key):
        print("Loading documents")

        for doc in data[root_key]["DOKUMENT"]:
            try:
                if "PRIPONKA" in doc.keys():
                    urls = get_values(doc["PRIPONKA"], "PRIPONKA_KLIC")
                    self.documents[doc["KARTICA_DOKUMENTA"]["UNID"]] = {
                        "title": doc["KARTICA_DOKUMENTA"]["KARTICA_NASLOV"],
                        "urls": urls,
                    }
                elif "KARTICA_URL_MAGNETOGRAM" in doc["KARTICA_DOKUMENTA"]:
                    self.magnetograms[doc["KARTICA_DOKUMENTA"]["UNID"]] = doc[
                        "KARTICA_DOKUMENTA"
                    ]["KARTICA_URL_MAGNETOGRAM"]
            except:
                print(doc)
                raise Exception("key_error")
        self.document_keys = self.documents.keys()

    def parse(
        self,
        session_number=None,
        session_type=None,
        parse_speeches=False,
        parse_votes=False,
    ):

        session_url_groups = [
            # TODO uncoment for parsing DZ sessions
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/SDZ.XML",
                "root_key": "SDZ",
                "file_name": "SDZ.XML",
                "sklc_type": "sej",
                "dz_url": "https://www.dz-rs.si/wps/portal/Home/seje/evidenca",
            },
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/SDT.XML",
                "root_key": "SDT",
                "file_name": "SDT.XML",
                "sklc_type": "dt",
                "dz_url": "https://www.dz-rs.si/wps/portal/Home/seje/evidenca",
            },
        ]

        for url_group in session_url_groups:
            response = requests.get(url_group["url"])
            with open(f'/tmp/{url_group["file_name"]}', "wb") as f:
                f.write(response.content)
            with open(f'/tmp/{url_group["file_name"]}', "rb") as data_file:
                data = xmltodict.parse(data_file, dict_constructor=dict)

            # load documents from XML
            self.load_documents(data, url_group["root_key"])

            # load type of subjects
            num_of_session = len(data[url_group["root_key"]]["SEJA"])
            for index, session in enumerate(
                list(reversed(data[url_group["root_key"]]["SEJA"]))
            ):
                print()
                print("New session")
                # print(session['KARTICA_SEJE']['KARTICA_OZNAKA'])
                full_session_name = session["KARTICA_SEJE"]["KARTICA_OZNAKA"]
                session_name = session["KARTICA_SEJE"]["KARTICA_OZNAKA"].lstrip("0")
                session_type_xml = session["KARTICA_SEJE"]["KARTICA_VRSTA"]
                organization_name = session["KARTICA_SEJE"]["KARTICA_STATUS"]
                print(f"parsing session {index}/{num_of_session}")

                start_time = None

                session_needs_editing = False

                if not session_name:
                    print("Session has unvalid name")
                    continue

                try:
                    if (
                        session_number and int(session_name) != int(session_number)
                    ) or (session_type and session_type_xml != session_type):
                        print("skip session")
                        continue
                except:
                    continue

                uid = session["KARTICA_SEJE"]["UNID"].split("|")[1]

                session_documents = session.get("PODDOKUMENTI", [])
                document_unids = get_values(session_documents)

                sklic_seje_unid = None
                for doc_unid in document_unids:
                    if doc_unid in self.document_keys:
                        document = self.documents[doc_unid]
                        if document["title"] and document["title"] == "Sklic seje":
                            sklic_seje_unid = doc_unid.split("|")[1]
                            break
                if not sklic_seje_unid:
                    print("Session has no sklic seje")
                    continue

                session_url = f'{url_group["dz_url"]}?mandat={self.storage.MANDATE_GOV_ID}&type={url_group["sklc_type"]}&uid={sklic_seje_unid}'

                sklic_url = session_url
                print("---> sklic_url:", sklic_url)
                sklic_content = requests.get(sklic_url).content
                sklic_htree = html.fromstring(sklic_content)
                print(session["KARTICA_SEJE"])

                body_session_name = self.find_session_name_from_table(sklic_htree)
                body_name, session_name_from_page = body_session_name.split("/")
                session_needs_editing = (
                    True
                    if session_name_from_page
                    and "(skupna seja)" in session_name_from_page
                    else False
                )

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

                print(session)

                speech_pages = session.get("DOBESEDNI_ZAPISI_SEJE", [])
                speech_unids = get_values(speech_pages)

                if organization_name and url_group["root_key"] == "SDT":
                    organization = self.storage.organization_storage.get_or_add_object(
                        {
                            "name": organization_name
                            # + " "
                            # + self.storage.MANDATE_GOV_ID,
                        }
                    )
                    organization_id = organization.id
                    org_gov_id = organization.gov_id
                    org_gov_id_short = org_gov_id[2:]
                    if org_gov_id_short[0] == "0":
                        org_gov_id_short = org_gov_id_short[1:]
                    session_gov_id = f"{self.storage.MANDATE_GOV_ID} {org_gov_id_short} - {organization_name.strip()} - {full_session_name}. {session_type_xml}"
                else:
                    organization_id = self.storage.main_org_id
                    org_gov_id = None
                    session_gov_id = f"{self.storage.MANDATE_GOV_ID} Državni zbor - {session_name.zfill(2)}. {session_type_xml}"

                # get or add session
                data = {
                    "name": f"{session_name}. {session_type_xml.lower()} seja",
                    "organization": organization_id,
                    "organizations": [organization_id],
                    "classification": self.get_session_type(session_type_xml),
                    "in_review": True,
                    "needs_editing": session_needs_editing,
                    "gov_id": session_gov_id,
                    "mandate_id": self.storage.mandate_id,
                }

                # workaround for sessions without date on sklic (DZ sessions)
                if start_time:
                    data["start_time"] = start_time.isoformat()
                current_session = self.storage.session_storage.get_or_add_object(data)
                session_id = current_session.id
                if (not current_session.start_time) and start_time:
                    # patch session start_time if is changed on dz page
                    current_session.update_start_time(start_time)

                print(
                    f"Getted session: {session_name}. {session_type_xml.lower()} seja has id {session_id}"
                )

                if current_session.is_new and document_unids:
                    for doc_unid in document_unids:
                        if doc_unid in self.document_keys:
                            document = self.documents[doc_unid]
                            doc_title = document["title"]
                            for doc_url in document["urls"]:
                                link_data = {
                                    "session": session_id,
                                    "url": doc_url,
                                    "name": doc_title,
                                }
                                self.storage.parladata_api.links.set(link_data)

                # parsing SPEECHES
                print("parse speeches?: ", parse_speeches)
                if parse_speeches:
                    start_order = 0
                    speech_urls = []
                    for orginal_speech_unid in speech_unids:
                        try:
                            speech_urls.append(self.magnetograms[orginal_speech_unid])
                        except:
                            pass

                    print("speech_unids")
                    print(speech_unids)

                    speech_parser = SpeechParser(
                        self.storage, speech_urls, current_session, start_time
                    )
                    speech_parser.parse()

    def get_session_type(self, type_text):
        type_text = type_text.lower().strip()
        return SESSION_TYPES.get(type_text.lower(), "unknown")

    def find_session_name_from_table(self, sklic_tree):
        for tr in sklic_tree.cssselect("table.table-custom>tr"):
            td = tr.cssselect("td")
            try:
                if td[0].text == "Polni naziv telesa / št. in vrsta seje":
                    span = td[1].cssselect("span")
                    if span:
                        return span[0].text
                    else:
                        return td[1].text
            except Exception as e:
                print(e)
        return None

    def find_date_form_table(self, sklic_tree):
        datetime_str = None
        for tr in sklic_tree.cssselect("table.table-custom>tr"):
            td = tr.cssselect("td")
            try:
                if td[0].text == "Datum in ura":
                    span = td[1].cssselect("span")
                    if span:
                        datetime_str = span[0].text
                    else:
                        datetime_str = td[1].text
            except Exception as e:
                print(e)

        if datetime_str:
            # date is: 22. 1. 2025 15:30
            if re.match(r"\d{1,2}\. \d{1,2}\. \d{4} \d{1,2}:\d{2}", datetime_str):
                return datetime.strptime(datetime_str, "%d. %m. %Y %H:%M")
            else:
                # find just date form string like: 20. 6. 2025 15 minut po končani 32. seji Državnega zbora
                date_match = re.search(r"\d{1,2}\. \d{1,2}\. \d{4}", datetime_str)
                if date_match:
                    date_str = date_match.group(0)
                    return datetime.strptime(date_str, "%d. %m. %Y")
        return None


# Odločitve
"""
parser za govore:
* sparsa govor v pregledu. In nato ko seja ni več v pregledu ga še enktat sparsa. Vse govore seje unvalidira in shrani nove.
* parser za govore se poganja samo 1x na dan ponoči
* shrani si koliko govorov je na seji in doparsaj nove govore.
"""
