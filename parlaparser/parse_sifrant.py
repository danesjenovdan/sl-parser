import re
from collections import defaultdict
from datetime import datetime

import requests
import xmltodict

from settings import MANDATE_STARTIME


class MembershipsParser(object):

    MONTHS = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "maj": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "avg": 8,
        "sep": 9,
        "okt": 10,
        "nov": 11,
        "dec": 12,
    }

    def __init__(self, storage):
        self.storage = storage
        self.storage.membership_storage.load_data()

    def parse(self):

        active_memberships = defaultdict(list)

        group_classifications = {
            "deputy group": "pg",
            "committee": "committee",
            "drugo": "other",
            "skupina prijateljstva": "friendship_group",
        }

        connection_types = {
            #'C': 'koordinator',
            "CL": "member",
            #'NC': 'deputy member',
            #'NDC': 'Alternate member',
            #'NP': None,
            "NPP": "deputy",
            #'NSDZ': 'Deputy Secretary General',
            #'NV': 'Deputy Leader',
            #'NVSL': 'Deputy Head of Service',persident
            "PDZ": "president",  #'president of National Assembly',
            "POS": "deputy",
            "PP": "deputy",  #'Deputy Chair',
            "PPDZ": "deputy",  # 'Vice-President of National Assembly',
            "PR": "president",
            #'SCL': 'stalni član',
            #'SDZ': 'Secretary General of the National Assembly',
            #'SE': 'Secretary',
            "SEPS": "deputy",  #'Deputy Group Secretary',
            #'TDZ': 'Secretary of the National Assembly',
            #'VK': 'Head of the Office of the President',
            #'VO': 'Leader',
            #'VOD': 'Head of Section',
            #'VS': 'Head of Division',
            #'VSE': 'Head of Division - Secretary',
            #'VSL': 'Head of Office'
        }
        connections = []
        org_key_id = {}
        subject_types = {}
        ps_keys = []

        url = f"https://fotogalerija.dz-rs.si/datoteke/opendata/SIF.XML"
        response = requests.get(url)
        with open(f"/tmp/SIF.XML", "wb") as f:
            f.write(response.content)
        with open("/tmp/SIF.XML", "rb") as data_file:
            data = xmltodict.parse(data_file, dict_constructor=dict)

            print(data["SIF"].keys())

            # load type of subjects
            for tip in data["SIF"]["TIPI_SUBJEKTOV"]["TIP_SUBJEKTA"]:
                tip_subjekta = self.get_root_or_text(tip["TIP_SUBJEKTA_NAZIV"], "AN")
                subject_types[tip["TIP_SUBJEKTA_SIFRA"]] = tip_subjekta

            """
            D Drugo
            DT Committee
            F Funkcija
            PS Deputy group
            SD Stalna delegacija
            SP Skupina prijateljstva
            """

            # connection_types are hardcoded for save just memberships which is needet for parlameter
            # # load type of connections
            # for tip in data['SIF']['TIPI_POVEZAV']['TIP_POVEZAVE']:
            #     connection_types[tip['TIP_POVEZAVE_SIFRA']] = self.get_root_or_text(tip['TIP_POVEZAVE_NAZIV']['M'], 'AN')

            # add people
            print("Adding people")
            for person in data["SIF"]["OSEBE"]["OSEBA"]:
                # continue
                name = f'{person["OSEBA_IME"]} {person["OSEBA_PRIIMEK"]}'

                izkaznica_string = self.get_root_or_text(
                    person["OSEBA_OSEBNA_IZKAZNICA"]
                )
                try:
                    birth_date = self.parse_birth_string(izkaznica_string)
                except:
                    birth_date = None
                # TODO create parsing gender [parladata api] person['OSEBA_SPOL']
                # TODO okraj [parladata api] person['OSEBA_POSLANSKI_MANDAT']['POSLANSKI_MANDAT_OKRAJ_NAZIV']
                # TODO update parsername with OSEBA_SIFRA if person exists
                new_person = self.storage.people_storage.get_or_add_object(
                    {
                        "parser_names": f'{name}|{person["OSEBA_SIFRA"]}',
                        "name": name,
                        "date_of_birth": birth_date,
                    }
                )
                # update existing person with GOV ID
                # if not new_person.is_new:
                #   new_person.add_parser_name(person["OSEBA_SIFRA"])

            # add groups
            print("Adding groups")
            for group in data["SIF"]["SUBJEKTI_FUNKCIJE"]["SUBJEKT_FUNKCIJA"]:
                subject_type_key = group["SUBJEKT_FUNKCIJA_TIP"]

                # Skip subjects pf type [Drugo, Funkcija, Stalna Delegacija, Skupina poslank in poslancev]
                if subject_type_key in ["D", "F", "SD", "SK"]:
                    continue
                subject_type_str = subject_types[subject_type_key]
                name = self.get_root_or_text(group["SUBJEKT_FUNKCIJA_NAZIV"])
                if "SUBJEKT_FUNKCIJA_DATUM_USTANOVITVE" in group.keys():
                    founding_date = datetime.strptime(
                        group["SUBJEKT_FUNKCIJA_DATUM_USTANOVITVE"], "%Y-%M-%d"
                    ).isoformat()
                else:
                    None
                acronym = group.get("SUBJEKT_FUNKCIJA_NAZIV", None)
                if subject_type_key == "PS":
                    ps_keys.append(group["SUBJEKT_FUNKCIJA_SIFRA"])

                classification = group_classifications[subject_type_str.lower()]
                if classification not in ["committee", "friendship_group"]:
                    continue

                group_data = {
                    "name": f"{name}",
                    "parser_names": f'{name}|{group["SUBJEKT_FUNKCIJA_SIFRA"]}',
                    "gov_id": group["SUBJEKT_FUNKCIJA_SIFRA"],
                    "classification": classification,
                    "founding_date": founding_date,
                }
                if acronym:
                    group_data.update({"acronym": acronym})
                organization = self.storage.organization_storage.get_or_add_object(
                    group_data,
                )
                org_key_id[group["SUBJEKT_FUNKCIJA_SIFRA"]] = organization.id

            # add memberships
            print("Adding memberships")
            org_keys = org_key_id.keys()
            print(ps_keys, len(ps_keys))
            for connection in data["SIF"]["POVEZAVE"]["POVEZAVA"]:
                # skip adding membership if subject type is in [Drugo, Funkcija, Stalna Delegacija]
                if connection["SUBJEKTI_FUNKCIJA_SIFRA"] not in org_keys:
                    continue

                person_gov_id = connection["OSEBA_SIFRA"]
                org_gov_id = connection["SUBJEKTI_FUNKCIJA_SIFRA"]

                print(person_gov_id, org_gov_id)

                person = self.storage.people_storage.get_or_add_object(
                    {"name": person_gov_id},
                    add=False,
                )
                # dont add memberships for people which not in ['SIF']['OSEBE']
                if not person:
                    continue

                # organization = self.storage.organization_storage.get_or_add_object(
                #     org_gov_id
                # )
                organization_id = org_key_id[org_gov_id]

                role = connection_types.get(connection["POVEZAVA_SIFRA"], None)
                if role:
                    print("Add or get person")
                    membership = self.storage.membership_storage.get_or_add_object(
                        {
                            "member": person.id,
                            "organization": organization_id,
                            "on_behalf_of": None,
                            "start_time": datetime.now().isoformat(),
                            "role": role,
                            "mandate": self.storage.mandate_id,
                        }
                    )
                    active_memberships[organization_id].append(membership.id)
            for i, membership_ids in active_memberships.items():
                organization = self.storage.organization_storage.get_organization_by_id(
                    i
                )
                for membership in organization.memberships:
                    if not membership.end_time:
                        if not membership.id in membership_ids:
                            membership.set_end_time(datetime.now().isoformat())
        return data

    def get_root_or_text(self, data, element="#text"):
        if isinstance(data, str):
            return data
        elif isinstance(data, dict):
            if element in data.keys():
                return data[element]
            elif "#text" in data.keys():
                return data["#text"]
            elif "AN" in data.keys():
                return data["AN"]
            else:
                return data
        else:
            print("-------CHECK THIS------", data)
            return data

    def parse_birth_string(self, data):
        birth_date_str_month_regex = r"\b[0-9]{1,2}. [A-Za-z]+ [0-9]{4}"
        birth_date_regex = r"\b[0-9]{1,2}. [0-9]{1,2}. [0-9]{4}"
        data = data.lower()
        birth_string = re.findall(birth_date_regex, data)
        birth_month_string = re.findall(birth_date_str_month_regex, data)
        if birth_month_string:
            birth_string = birth_month_string[0]
            month = birth_string.split(" ")[1]
            month_number = self.MONTHS[month[:3]]
            birth_string = birth_string.replace(month, str(month_number) + ".")
            birth_date = (
                datetime.strptime(birth_string, "%d. %m. %Y").date().isoformat()
            )
        elif birth_string:
            birth_string = birth_string[0]
            birth_date = (
                datetime.strptime(birth_string, "%d. %m. %Y").date().isoformat()
            )
        else:
            birth_date = None
        return birth_date
