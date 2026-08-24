import locale
import re
from datetime import datetime
from enum import Enum

import requests
import sentry_sdk
import xmltodict
from lxml import html

from parlaparser.utils.methods import get_values
from settings import BASE_URL, MANDATE_GOV_ID


class LegislationParser(object):
    def __init__(self, storage):
        self.storage = storage
        self.legislation_storage = self.storage.legislation_storage
        self.amendment_storage = self.storage.amendment_storage
        locale.setlocale(locale.LC_TIME, "sl_SI.utf-8")
        self.documents = {}

    def load_documents(self, data, key="PZ"):
        print("Loading documents")

        documents = data[key].get("DOKUMENT", [])

        for o_doc in documents:
            doc = o_doc["KARTICA_DOKUMENTA"]

            sub_doc = o_doc["PODDOKUMENTI"]
            if "PRIPONKA" in doc.keys():
                urls = get_values(doc["PRIPONKA"], "PRIPONKA_KLIC")
                vote = doc.get("GLASOVANJE", None)
                if vote:
                    vote_date = vote.get("GLASOVANJE_CAS", None)
                self.documents[doc["UNID"]] = {
                    "title": doc["KARTICA_NAZIV"],
                    "urls": urls,
                    "epa": doc.get("KARTICA_EPA", None),
                    "type": doc.get("KARTICA_VRSTA", None),
                    "author": doc.get("KARTICA_AVTOR", None),
                    "abbreviation": doc.get("KARTICA_KRATICA", None),
                    "date": doc.get("KARTICA_DATUM", None),
                    "vote_date": vote_date if vote else None,
                }
            elif sub_doc:
                vote = doc.get("GLASOVANJE", None)
                if vote:
                    vote_date = vote.get("GLASOVANJE_CAS", None)
                self.documents[doc["UNID"]] = {
                    "title": doc["KARTICA_NAZIV"],
                    "sub-docs": sub_doc["UNID"],
                    "epa": doc.get("KARTICA_EPA", None),
                    "type": doc.get("KARTICA_VRSTA", None),
                    "author": doc.get("KARTICA_AVTOR", None),
                    "abbreviation": doc.get("KARTICA_KRATICA", None),
                    "date": doc.get("KARTICA_DATUM", None),
                    "vote_date": vote_date if vote else None,
                }
            else:
                vote = doc.get("GLASOVANJE", None)
                if vote:
                    vote_date = vote.get("GLASOVANJE_CAS", None)
                self.documents[doc["UNID"]] = {
                    "title": doc["KARTICA_NAZIV"],
                    "urls": None,
                    "epa": doc.get("KARTICA_EPA", None),
                    "type": doc.get("KARTICA_VRSTA", None),
                    "author": doc.get("KARTICA_AVTOR", None),
                    "abbreviation": doc.get("KARTICA_KRATICA", None),
                    "date": doc.get("KARTICA_DATUM", None),
                    "vote_date": vote_date if vote else None,
                }
            # except:
            #     print(doc)
            #     raise Exception("key_error")
        self.document_keys = self.documents.keys()
        print(len(self.documents.keys()), " documetns loaded")

    def parse(self):
        print("Start parsing")
        self.mandate = f"-{MANDATE_GOV_ID}"
        urls = [
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/PZ.XML",
                "type": "law",
                "file_name": "PZ.XML",
                "xml_key": "PZ",
                "amendment_url": "https://www.dz-rs.si/wps/portal/Home/zakonodaja/izbran/!ut/p/z1/?uid={}&db=pre_zak&mandat={}&tip=doc",
            },
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/PZ10.XML",
                "type": "law",
                "file_name": "PZ10.XML",
                "xml_key": "PZ",
                "amendment_url": "https://www.dz-rs.si/wps/portal/Home/zakonodaja/izbran/!ut/p/z1/?uid={}&db=pre_zak&mandat={}&tip=doc",
            },
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/PA.XML",
                "type": "act",
                "file_name": "PA.XML",
                "xml_key": "PA",
                "amendment_url": None,
            },
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/PA10.XML",
                "type": "act",
                "file_name": "PA10.XML",
                "xml_key": "PA",
                "amendment_url": None,
            },
        ]
        result_urls = [
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/SA.XML",
                "type": "act",
                "file_name": "SA.XML",
                "xml_key": "SA",
                "amendment_url": None,
            },
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/SZ.XML",
                "type": "law",
                "file_name": "SZ.XML",
                "xml_key": "SZ",
                "amendment_url": "https://www.dz-rs.si/wps/portal/Home/zakonodaja/izbran/!ut/p/z1/?uid={}&db=kon_zak&mandat={}&tip=doc",
            },
        ]
        for legislation_file in urls:
            print("parse file: ", legislation_file["file_name"])
            response = requests.get(legislation_file["url"])
            with open(f'/tmp/{legislation_file["file_name"]}', "wb") as f:
                f.write(response.content)
            with open(f'/tmp/{legislation_file["file_name"]}', "rb") as data_file:
                data = xmltodict.parse(data_file, dict_constructor=dict)

            # load documents from XML
            self.load_documents(data, legislation_file["xml_key"])
            self.parse_xml_data(
                data, legislation_file, array_key="PREDPIS", obj_key="KARTICA_PREDPISA"
            )
            self.parse_xml_data(
                data,
                legislation_file,
                array_key="OBRAVNAVA_PREDPISA",
                obj_key="KARTICA_OBRAVNAVE_PREDPISA",
            )
            if legislation_file["amendment_url"]:
                self.parse_amendments(legislation_file)

        for enacted_law in result_urls:
            print("parse file: ", enacted_law["file_name"])
            response = requests.get(enacted_law["url"])
            with open(f'/tmp/{enacted_law["file_name"]}', "wb") as f:
                f.write(response.content)
            with open(f'/tmp/{enacted_law["file_name"]}', "rb") as data_file:
                data = xmltodict.parse(data_file, dict_constructor=dict)
            self.parse_xml_data(
                data, enacted_law, array_key="PREDPIS", obj_key="KARTICA_PREDPISA"
            )

    def parse_amendments(self, legislation_file):
        # self = lb
        field_mappings = {
            "Naslov zadeve": "title",
            "Datum vložitve": "timestamp",
            "Datum glasovanja": "vote_date",
        }
        for unid, document in self.documents.items():
            if document["type"] == "Amandma":
                uid = unid.split("|")[1]
                amendment_data = {
                    "mandate": self.storage.mandate_id,
                    "uid": uid,
                }
                print("Before check", amendment_data)
                if self.amendment_storage.check_if_amendment_is_parsed(amendment_data):
                    print("amendment is alredy parsed")
                    # TODO: check for updates in amendment data and update if needed
                    continue
                else:
                    # parse data from XML
                    epa = self.remove_leading_zeros(document.get("epa", None))
                    if not epa or self.mandate not in epa:
                        continue
                    amendment_data.update(
                        {
                            "title": document["title"],
                            "epa": epa,
                            "abbreviation": document.get("abbreviation", None),
                            "proposer_text": document.get("author", None),
                            "timestamp": datetime.strptime(
                                document["date"], "%Y-%m-%d"
                            ).isoformat(),
                            "timestamp_vote": document["vote_date"],
                        }
                    )

                    # parse data from page
                    page_url = legislation_file["amendment_url"].format(
                        uid, MANDATE_GOV_ID
                    )
                    response = requests.get(page_url)
                    print("Amendment page URL:", page_url)
                    if response.status_code != 200:
                        print(f"Failed to fetch amendment page for {uid}")
                        continue
                    sklic_htree = html.fromstring(response.content)
                    trs = sklic_htree.cssselect("table.table-custom>tr")
                    data = {}
                    for tr in trs:
                        tds = tr.cssselect("td")
                        if len(tds) < 2:
                            print(
                                "Skipping row with insufficient columns:",
                                tr.text_content(),
                            )
                            continue
                        key = tds[0].text_content().strip()
                        value = tds[1].text_content().strip()
                        data[key] = value
                    amendment_data.update(self.parse_amendment_web_field(data))
                    amendment_content = sklic_htree.cssselect("div.paper-text")
                    if amendment_content:
                        text_content = amendment_content[0].text_content()
                    else:
                        print(
                            "Amendmen page is empty for",
                            document,
                            legislation_file["file_name"],
                        )
                        continue
                    amendment_data.update({"content": text_content})
                    if "result" in amendment_data:
                        amendment_data["result"] = self.parse_amendment_result(
                            amendment_data["result"]
                        )
                    if "procedure_type" in amendment_data:
                        procedure_type = (
                            self.legislation_storage.get_or_add_procedure_type(
                                amendment_data["procedure_type"]
                            )
                        )
                        if procedure_type:
                            amendment_data["procedure_type"] = procedure_type.id
                    if "procedure_phase" in amendment_data:
                        procedure_phase = (
                            self.legislation_storage.get_or_add_procedure_phase(
                                amendment_data["procedure_phase"]
                            )
                        )
                        if procedure_phase:
                            amendment_data["procedure_phase"] = procedure_phase.id

                    if "proposer_text" in amendment_data:
                        orgs = []
                        proposers = amendment_data["proposer_text"].split(";")
                        print("Processing proposers:", proposers)
                        for proposer in proposers:
                            proposer = proposer.split("-")
                            if len(proposer) > 1:
                                proposer = proposer[1].strip()
                            else:
                                proposer = proposer[0].strip()

                            if proposer.startswith("Poslanska skupina"):
                                proposer_org = (
                                    self.storage.organization_storage.get_or_add_object(
                                        {"name": proposer}
                                    )
                                )
                                orgs.append(proposer_org.id)
                        amendment_data["proposed_by_organizations"] = orgs

                    if "epa" in amendment_data:
                        law = self.legislation_storage.get_or_add_object(
                            {
                                "epa": amendment_data.pop("epa").lstrip("0"),
                                "mandate": self.storage.mandate_id,
                            }
                        )
                        amendment_data["legislation"] = law.id

                    self.amendment_storage.get_or_add_object(amendment_data)

    def parse_amendment_web_field(self, fields):
        field_mappings = {
            # "Vrsta dokumenta": "",
            # "Naslov zadeve": "title",
            # "Datum vložitve": "timestamp",
            # "EPA": "epa",
            # "Kratica": "abbreviation",
            "Faza": "procedure_phase",
            "Vrsta postopka": "procedure_type",
            # "Predlagatelj": "proposer_text",
            "Odločitev": "result",
            "Zveza": "reference",
            "Obrazložitev": "explanation",
        }
        data = {}
        for key, value in fields.items():
            if key in field_mappings:
                data[field_mappings[key]] = value
        return data

    def parse_amendment_result(self, result):
        try:
            result_key = amendments_results[result]
        except KeyError:
            result_key = result
        result_obj = self.storage.amendment_storage.get_or_add_amendment_result(
            result_key
        )
        return result_obj.id

    def parse_amendment_authors(self, authors):
        # TODO
        if isinstance(authors, list):
            return [author for author in authors]
        else:
            return [authors]

    def get_procedured(data, legislation_file, array_key, obj_key):
        """
        helper method for get procedure phases
        """
        phases = []
        try:
            legislation_list = data[legislation_file["xml_key"]][array_key]
        except Exception as e:
            print(legislation_file)
            print(data.keys())
            raise e

        for wraped_legislation in legislation_list:
            legislation = wraped_legislation[obj_key]
            legislation_procedure_phase = legislation["KARTICA_FAZA_POSTOPKA"]
            phases.append(legislation_procedure_phase)
        return list(set(phases))

    def parse_xml_data(self, data, legislation_file, array_key, obj_key):
        # load type of subjects
        try:
            legislation_list = data[legislation_file["xml_key"]][array_key]
        except Exception as e:
            print(legislation_file)
            print(data.keys())
            print(e)
            return
        for wraped_legislation in legislation_list:
            legislation = wraped_legislation[obj_key]

            if "KARTICA_EPA" not in legislation or not legislation["KARTICA_EPA"]:
                print("KARTICA_EPA not found in legislation:", wraped_legislation)
                continue
            epa = self.remove_leading_zeros(legislation["KARTICA_EPA"])
            if not epa or self.mandate not in epa:
                continue

            title = legislation["KARTICA_NAZIV"]
            unid = legislation["UNID"]
            date = legislation["KARTICA_DATUM"]
            champion = legislation["KARTICA_PREDLAGATELJ"]
            champion_wb = legislation["KARTICA_DELOVNA_TELESA"]
            legislation_procedure_type = legislation["KARTICA_POSTOPEK"]
            legislation_procedure_phase = legislation["KARTICA_FAZA_POSTOPKA"]
            legislation_session = legislation.get("KARTICA_SEJA", None)
            if date:
                date_iso = datetime.strptime(date, "%Y-%m-%d").isoformat()
            else:
                date_iso = None

            legislation_documents = wraped_legislation.get("PODDOKUMENTI", [])
            document_unids = get_values(legislation_documents)

            if legislation_session:
                legislation_session = legislation_session.strip("0").lower() + " seja"

            if champion_wb:
                champion_wb = self.storage.organization_storage.get_or_add_object(
                    {"name": champion_wb}
                ).id
            else:
                champion_wb = None

            connected_legislation = wraped_legislation.get("POVEZANI_PREDPISI", [])
            connected_legislation_unids = get_values(connected_legislation)

            if array_key == "PREDPIS":  # legislation
                print("PREDPIS", epa, legislation_procedure_type)
                legislation_procedure_type_pk = (
                    self.legislation_storage.get_or_add_procedure_type(
                        legislation_procedure_type
                    ).id
                )
                law_data = {
                    "text": title,
                    "epa": epa,
                    "uid": unid,
                    "proposer_text": champion,
                    "procedure_type": legislation_procedure_type_pk,
                    "mdt_fk": champion_wb,
                    "timestamp": date_iso,
                    "classification": self.legislation_storage.get_legislation_classifications_by_name(
                        legislation_file["type"]
                    ),
                    "mandate": self.storage.mandate_id,
                }
                self.add_or_update_legislation(law_data, document_unids)
            else:  # legislation consideration
                procedure_org = (
                    champion_wb
                    if "MDT" in legislation_procedure_phase
                    else self.storage.main_org_id
                )
                data = {
                    "epa": epa,
                    "uid": unid,
                    "organization": procedure_org,
                    "timestamp": date_iso,
                    "consideration_phase": legislation_procedure_phase,
                    "session": None,
                }
                if legislation_session and champion_wb:
                    session = self.storage.session_storage.get_object_or_none(
                        {
                            "name": legislation_session,
                            "organizations": [procedure_org],
                        }
                    )
                    if session:
                        data.update(session=session.id)
                legislation_consideration = (
                    self.prepare_data_and_set_legislation_consideration(data)
                )
                if legislation_consideration.is_new:
                    """
                    if is new legislation consideration set documents and legislation status
                    """
                    self.add_docs(
                        document_unids,
                        {"legislation_consideration": legislation_consideration.id},
                    )

                    if legislation_procedure_phase.strip() == "konec postopka":
                        self.legislation_storage.set_law_as_rejected(epa)
                    elif legislation_procedure_phase.strip() == "sprejet predlog":
                        # check if procedure is call for referendum
                        is_referendum = any(
                            [
                                [
                                    self.get_doc_title(c_unid)
                                    == "Pobuda za zakonodajni referendum"
                                    for c_unid in document_unids
                                ]
                            ]
                        )

                        if is_referendum:
                            self.legislation_storage.set_law_as_in_procedure(epa)
                        else:
                            self.legislation_storage.set_law_as_enacted(epa)
                    elif (
                        legislation_procedure_phase.strip()
                        == "zahteva za ponovno odločanje"
                    ):
                        self.legislation_storage.set_law_as_in_procedure(epa)

    def parser_results_xml(self, data, legislation_file, array_key, obj_key):
        try:
            legislation_list = data[legislation_file["xml_key"]][array_key]
        except:
            print(legislation_file)
            print(data.keys())
            raise Exception()

        for wraped_legislation in legislation_list:
            legislation = wraped_legislation[obj_key]
            epa = self.remove_leading_zeros(legislation["KARTICA_EPA"])
            mandat = legislation["KARTICA_MANDAT"]
            if self.mandate in epa:
                self.legislation_storage.set_law_as_enacted(epa=epa)

    def prepare_data_and_set_legislation_consideration(self, legislation_consideration):
        law = self.legislation_storage.get_or_add_object(
            {
                "epa": legislation_consideration["epa"],
                "mandate": self.storage.mandate_id,
            }
        )
        procedure_phase = self.legislation_storage.get_procedure_phase(
            {"name": legislation_consideration.pop("consideration_phase")}
        )
        if not procedure_phase:
            sentry_sdk.capture_message(
                f"There is new procedure phase {legislation_consideration.pop('consideration_phase')}"
            )
            return

        # organization_name = legislation_consideration['organization']
        # if organization_name:
        #     organization = self.storage.organization_storage.get_or_add_object({
        #         "name": organization_name,
        #     })
        #     organization_id = organization.id
        # else:
        #     organization_id = None

        legislation_consideration.update(
            {
                "procedure_phase": procedure_phase.id,
                "legislation": law.id,
            }
        )
        # print(legislation_consideration)
        return self.legislation_storage.prepare_and_set_legislation_consideration(
            legislation_consideration
        )

    def add_or_update_legislation(self, legislation_obj, document_unids):
        print("add or update legislation", legislation_obj)
        law = self.legislation_storage.update_or_add_law(legislation_obj)
        # if law.is_new:
        self.add_docs(document_unids, {"legislation": law.id})

    def get_doc_title(self, document_unid):
        if not document_unid:
            return ""

        if document_unid in self.document_keys:
            return self.documents[document_unid]["title"]
        return None

    def add_docs(self, document_unids, document_parent_object):
        if not document_unids:
            return
        if "legislation" in document_parent_object:
            ex_urls = [
                link["url"]
                for link in self.legislation_storage.get_legislation_docs(
                    legislation_id=document_parent_object["legislation"]
                )
            ]
        else:
            ex_urls = []
        for doc_unid in document_unids:
            if doc_unid in self.document_keys:
                document = self.documents[doc_unid]
                doc_title = document["title"]
                tags = []
                if doc_title:
                    if "pobuda za zakonodajni referendum" in doc_title.lower():
                        tags.append("referendum")
                    elif "besedilo predloga zakona" in doc_title.lower():
                        tags.append("proposal")
                    elif "Besedilo zakona poslano Uradnemu listu" in doc_title:
                        tags.append("enacted")
                if "urls" in document.keys() and document["urls"]:
                    for doc_url in document["urls"]:
                        if doc_url in ex_urls:
                            continue
                        link_data = {"url": doc_url, "name": doc_title, "tags": tags}
                        link_data.update(document_parent_object)
                        self.storage.parladata_api.links.set(link_data)
                elif "sub-docs" in document.keys():
                    self.add_docs(document["sub-docs"], document_parent_object)

    def remove_leading_zeros(self, word, separeted_by=[",", "-", "/"]):
        if not word:
            return None
        for separator in separeted_by:
            word = separator.join(
                map(lambda x: x.lstrip("0"), word.split(separator))
            ).strip()
        return word


# OBRAVNAVA_PREDPISA -> KARTICA_FAZA_POSTOPKA
faze = [
    "Zakonodajni referendum",
    "druga obravnava - DZ",
    "druga obravnava - MDT",
    "druga obravnava DZ - nujni postopek",
    "druga obravnava DZ - skrajšani postopek",
    "druga obravnava MDT - nujni postopek",
    "druga obravnava MDT - skrajšani postopek",
    "konec postopka",
    "konec postopka - predstavitev",
    "konec postopka - seznanitev",
    "obravnava - DZ",
    "obravnava - MDT",
    "obravnava DZ - ratifikacija",
    "obravnava MDT - ratifikacija",
    "obravnava pobude",
    "obravnava postopka - nujni postopek",
    "obravnava postopka - skrajšani postopek",
    "prva faza",
    "prva obravnava",
    "sprejet predlog",
    "sprejet sklep",
    "tretja obravnava",
    "tretja obravnava - nujni postopek",
    "tretja obravnava - skrajšani postopek",
    "zahteva za ponovno odločanje",
]

# PREDPIS -> KARTICA_POSTOPEK
["sprejet predlog", "konec postopka"]

# for faza in faze:
#     ProcedurePhase(
#         procedure_id=1,
#         name=faza
#     ).save()

amendments_results = {
    "umaknjen": "withdrawn",
    "brezpredmeten": "pointless",
    "sprejet": "accepted",
    "nesprejet": "rejected",
    "nepravilno vložen": "improperly filed",
}
