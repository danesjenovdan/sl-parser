import requests
import sentry_sdk
import xmltodict

SESSION_TYPE = {
    "redna": "regular",
    "izredna": "irregular",
}

ROMAN_NUMERALS_MAP = {
    "9": "IX",
    "8": "VIII",
    "7": "VII",
    "6": "VI",
    "5": "V",
}


class VotesParser(object):
    def __init__(self, storage):
        self.storage = storage

    def parse(self):
        votes_url_groups = [
            # TODO uncoment for parsing DZ sessions
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/GDZ.XML",
                "file_name": "GDZ.XML",
                "type": "DZ",
            },
            {
                "url": "https://fotogalerija.dz-rs.si/datoteke/opendata/GDT.XML",
                "file_name": "GDT.XML",
                "type": "DT",
            },
        ]
        for url_group in votes_url_groups:
            response = requests.get(url_group["url"])
            with open(f'/tmp/{url_group["file_name"]}', "wb") as f:
                f.write(response.content)
            with open(f'/tmp/{url_group["file_name"]}', "rb") as data_file:
                data = xmltodict.parse(data_file, dict_constructor=dict)

            votes_list = data["GLASOVANJA_SEZNAM"]["GLASOVANJE"]

            for i, vote_xml in enumerate(votes_list):
                timestamp = vote_xml["GLASOVANJE_DATUM_CAS"].split(".")[0]
                vote_vrsta = vote_xml["VRSTA"]
                vote_vrsta_dokumenta = vote_xml["VRSTA_DOKUMENTA"]
                naslov_akta = vote_xml["NASLOV_AKTA"]
                vote_zveza = vote_xml["ZVEZA"]
                xml_mandate = vote_xml["MANDAT"]
                seja = vote_xml["SEJA"]
                if url_group["type"] == "DZ":
                    session_name_org = seja["ID"].strip()
                    session_name = session_name_org.strip("0")
                    session_name = f"{session_name.lower()} seja"
                    organization = (
                        self.storage.organization_storage.get_organization_by_id(
                            int(self.storage.main_org_id)
                        )
                    )
                    session_gov_id = f"{self.storage.MANDATE_GOV_ID} Državni zbor - {session_name_org}"
                else:
                    if not "DELOVNO_TELO" in seja.keys():
                        continue
                    session_full_name = seja["ID"].strip()
                    session_gov_id_short = " ".join(session_full_name.split(" ")[1:])
                    session_name = (
                        f'{session_gov_id_short.lower().strip("0").strip()} seja'
                    )
                    dt_splited = seja["DELOVNO_TELO"].split("-")
                    org_gov_id_short = dt_splited[0].strip()
                    org_name = "-".join(dt_splited[1:]).strip()
                    org_gov_id = f"DT{org_gov_id_short.strip().zfill(3)}"
                    organization = (
                        self.storage.organization_storage.get_organization_by_gov_id(
                            org_gov_id
                        )
                    )

                    session_gov_id = f"{self.storage.MANDATE_GOV_ID} {org_gov_id_short} - {org_name.strip()} - {session_gov_id_short}"

                session = self.storage.session_storage.get_or_add_object(
                    {
                        "name": session_name,
                        "gov_id": session_gov_id,
                        "organization": organization.id,
                        "timestamp": timestamp,
                        "classification": SESSION_TYPE.get(seja["VRSTA"], "unknown"),
                        "organizations": [organization.id],
                    }
                )

                if xml_mandate and xml_mandate.isdigit():
                    xml_mandate = ROMAN_NUMERALS_MAP.get(xml_mandate)

                epa = vote_xml.get("EPA")
                if epa:
                    epa = f"{epa}-{xml_mandate}"
                uid = None

                if session.vote_storage.check_if_motion_is_parsed(
                    {"datetime": timestamp}
                ):
                    print("this vote is already parsed")
                    continue

                if naslov_akta:
                    title = f"{naslov_akta} - {vote_zveza}"
                elif vote_vrsta:
                    title = vote_vrsta
                elif vote_zveza:
                    title = vote_zveza
                else:
                    print(vote_xml)
                    sentry_sdk.capture_message(
                        f"Vote without title vote_xml: {vote_xml} session_name: {session_name} timestamp: {timestamp}"
                    )
                    continue
                    raise Exception("No title")

                tocka = vote_xml["TOCKA"]
                vote_id = self.save_data(session, title, timestamp, timestamp, epa=epa)
                ballots = vote_xml["SEZNAM"]["VALUE"]
                self.save_ballots(session, vote_id, ballots)

    def save_data(self, session, title, start_time, uid, epa=""):
        legislation_id = None
        if epa:
            legislation = self.storage.legislation_storage.update_or_add_law(
                {
                    "epa": epa,
                    "mandate": self.storage.mandate_id,
                }
            )
            legislation_id = legislation.id

        motion = {
            "title": title,
            "text": title,
            "datetime": start_time,
            "session": session.id,
            "gov_id": uid,
        }
        if legislation_id:
            motion["law"] = legislation_id

        motion_obj = session.vote_storage.get_or_add_object(motion)

        vote_id = int(motion_obj.vote.id)
        return vote_id

    def save_ballots(self, session, vote_id, ballots):
        ballots_for_save = []
        for ballot_str in ballots:
            data = ballot_str.split("|")
            if len(data) == 3:
                name, kvorum, option = data
            else:
                name, pg, kvorum, option = data
            person = self.storage.people_storage.get_or_add_object({"name": name})
            person_option = ""
            if kvorum == "_":
                person_option = "absent"
            elif option == "_":
                person_option = "abstain"
            elif option == "P":
                person_option = "against"
            elif option == "Z":
                person_option = "for"
            else:
                raise Exception("Unkonwn option")
            ballots_for_save.append(
                {"personvoter": person.id, "option": person_option, "vote": vote_id}
            )
        session.vote_storage.set_ballots(ballots_for_save)
