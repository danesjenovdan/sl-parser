import requests
import xmltodict
import re
import locale
import sentry_sdk

from datetime import datetime

from lxml import html
from enum import Enum

from settings import BASE_URL, MANDATE_GOV_ID
from parlaparser.utils.methods import get_values


class LegislationParser(object):
    def __init__(self, storage):
        self.storage = storage
        self.legislation_storage =  self.storage.legislation_storage
        locale.setlocale(locale.LC_TIME, "sl_SI.utf-8")
        self.documents = {}

    def load_documents(self, data, key='PZ'):
        print('Loading documents')

        documents = data[key].get('DOKUMENT', [])

        for doc in documents:
            doc = doc['KARTICA_DOKUMENTA']
            try:
                if 'PRIPONKA' in doc.keys():
                    urls = get_values(doc['PRIPONKA'], 'PRIPONKA_KLIC')
                    self.documents[doc['UNID']] = {
                        'title': doc['KARTICA_NAZIV'],
                        'urls': urls
                    }
            except:
                print(doc)
                raise Exception('key_error')
        self.document_keys = self.documents.keys()
        print(len(self.documents.keys()), ' documetns loaded')

    def parse(self):
        print('Start parsing')
        self.mandate = MANDATE_GOV_ID
        urls = [
            {
                'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/PZ.XML',
                'type': 'law',
                'file_name': 'PZ.XML',
                'xml_key': 'PZ',
            },
            {
                'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/PZ9.XML',
                'type': 'law',
                'file_name': 'PZ9.XML',
                'xml_key': 'PZ',
            },
            {
                'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/PA.XML',
                'type': 'act',
                'file_name': 'PA.XML',
                'xml_key': 'PA',
            },
            {
                'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/PA9.XML',
                'type': 'act',
                'file_name': 'PA9.XML',
                'xml_key': 'PA',
            },
        ]
        result_urls= [
            {
                'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/SA.XML',
                'type': 'act',
                'file_name': 'SA.XML',
                'xml_key': 'SA',
            },
            {
                'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/SZ.XML',
                'type': 'law',
                'file_name': 'SZ.XML',
                'xml_key': 'SZ',
            },
        ]
        for legislation_file in urls:
            print('parse file: ', legislation_file["file_name"])
            response = requests.get(legislation_file['url'])
            with open(f'/tmp/{legislation_file["file_name"]}', 'wb') as f:
                f.write(response.content)
            with open(f'/tmp/{legislation_file["file_name"]}', 'rb') as data_file:
                data = xmltodict.parse(data_file, dict_constructor=dict)

            # load documents from XML
            self.load_documents(data, legislation_file['xml_key'])
            self.parse_xml_data(data, legislation_file, array_key='PREDPIS', obj_key='KARTICA_PREDPISA')
            self.parse_xml_data(data, legislation_file, array_key='OBRAVNAVA_PREDPISA', obj_key='KARTICA_OBRAVNAVE_PREDPISA')

        for enacted_law in result_urls:
            print('parse file: ', enacted_law["file_name"])
            response = requests.get(enacted_law['url'])
            with open(f'/tmp/{enacted_law["file_name"]}', 'wb') as f:
                f.write(response.content)
            with open(f'/tmp/{enacted_law["file_name"]}', 'rb') as data_file:
                data = xmltodict.parse(data_file, dict_constructor=dict)
            self.parse_xml_data(data, enacted_law, array_key='PREDPIS', obj_key='KARTICA_PREDPISA')


    def get_procedured(data, legislation_file, array_key, obj_key):
        """
        helper method for get procedure phases
        """
        phases = []
        try:
            legislation_list = data[legislation_file['xml_key']][array_key]
        except:
            print(legislation_file)
            print(data.keys())
            raise Exception()

        for wraped_legislation in legislation_list:
            legislation = wraped_legislation[obj_key]
            legislation_procedure_phase = legislation['KARTICA_FAZA_POSTOPKA']
            phases.append(legislation_procedure_phase)
        return list(set(phases))

    def parse_xml_data(self, data, legislation_file, array_key, obj_key):
        # load type of subjects
        try:
            legislation_list = data[legislation_file['xml_key']][array_key]
        except Exception as e:
            print(legislation_file)
            print(data.keys())
            print(e)
            return
        for wraped_legislation in legislation_list:
            legislation = wraped_legislation[obj_key]
            try:
                epa = self.remove_leading_zeros(legislation['KARTICA_EPA'])
                if self.mandate not in epa:
                    continue

                title = legislation['KARTICA_NAZIV']
                unid = legislation['UNID']
                date = legislation['KARTICA_DATUM']
                champion = legislation['KARTICA_PREDLAGATELJ']
                champion_wb = legislation['KARTICA_DELOVNA_TELESA']
                legislation_procedure_type = legislation['KARTICA_POSTOPEK']
                legislation_procedure_phase = legislation['KARTICA_FAZA_POSTOPKA']
                legislation_session = legislation.get('KARTICA_SEJA', None)
                if date:
                    date_iso = datetime.strptime(date, '%Y-%m-%d').isoformat()
                else:
                    date_iso = None

                legislation_documents = wraped_legislation.get('PODDOKUMENTI', [])
                document_unids = get_values(legislation_documents)

                if legislation_session:
                    legislation_session = legislation_session.strip('0').lower() + ' seja'

                if champion_wb:
                    champion_wb = self.storage.organization_storage.get_or_add_object(champion_wb).id

                connected_legislation = wraped_legislation.get('POVEZANI_PREDPISI', [])
                connected_legislation_unids = get_values(connected_legislation)
            except Exception as e:
                print('Boooooo')
                print(legislation)
                print(e)
                continue

            if array_key == 'PREDPIS': # legislation
                law_data = {
                    'text': title,
                    'epa': epa,
                    'uid': unid,
                    'proposer_text': champion,
                    'procedure_type': legislation_procedure_type,
                    'mdt_fk': champion_wb,
                    'timestamp': date_iso,
                    'classification': self.legislation_storage.get_legislation_classifications_by_name(legislation_file['type']),
                    'mandate': self.storage.mandate_id
                }
                self.add_or_update_legislation(
                    law_data,
                    document_unids
                )
                if legislation_procedure_phase.strip() == 'konec postopka':
                    self.legislation_storage.set_law_as_rejected(epa)
                elif legislation_procedure_phase.strip() == 'sprejet predlog':
                    self.legislation_storage.set_law_as_enacted(epa)
            else: # legislation consideration
                data = {
                    'epa': epa,
                    'uid': unid,
                    'organization': champion_wb,
                    'timestamp': date_iso,
                    'consideration_phase': legislation_procedure_phase
                }
                if legislation_session:
                    session_id = self.storage.session_storage.get_session_by_name(legislation_session)
                    if session_id:
                        data.update(session=session_id)
                try:
                    legislation_consideration = self.prepare_data_and_set_legislation_consideration(data)
                    if legislation_consideration.is_new:
                        self.add_docs(
                            document_unids,
                            {
                                'legislation_consideration': legislation_consideration.id
                            }
                        )
                except:
                    pass

    def parser_results_xml(self, data, legislation_file, array_key, obj_key):
        try:
            legislation_list = data[legislation_file['xml_key']][array_key]
        except:
            print(legislation_file)
            print(data.keys())
            raise Exception()

        for wraped_legislation in legislation_list:
            legislation = wraped_legislation[obj_key]
            epa = self.remove_leading_zeros(legislation['KARTICA_EPA'])
            mandat = legislation['KARTICA_MANDAT']
            if self.mandate in epa:
                self.legislation_storage.set_law_as_enacted(
                    epa=epa
                )

    def prepare_data_and_set_legislation_consideration(self, legislation_consideration):
        law = self.legislation_storage.update_or_add_law({
            'epa': legislation_consideration['epa']
        })
        procedure_phase = self.legislation_storage.get_procedure_phase({
            'name': legislation_consideration.pop('consideration_phase')
        })
        if not procedure_phase:
            sentry_sdk.capture_message(f"There is new procedure phase {legislation_consideration.pop('consideration_phase')}")
            return

        organization_name = legislation_consideration['organization']
        if organization_name:
            organization = self.storage.organization_storage.get_or_add_object({
                "name": organization_name,
            })
            organization_id = organization.id
        else:
            organization_id = None

        legislation_consideration.update({
            'organization': organization_id,
            'procedure_phase': procedure_phase.id,
            'legislation': law.id
        })
        return self.legislation_storage.prepare_and_set_legislation_consideration(legislation_consideration)

    def add_or_update_legislation(self, legislation_obj, document_unids):
        law = self.legislation_storage.update_or_add_law(legislation_obj)
        if law.is_new:
            self.add_docs(document_unids, {'legislation': law.id})


    def add_docs(self, document_unids, document_parent_object):
        if not document_unids:
            return
        for doc_unid in document_unids:
            if doc_unid in self.document_keys:
                document = self.documents[doc_unid]
                doc_title = document['title']
                for doc_url in document['urls']:
                    link_data = {
                        'url': doc_url,
                        'name': doc_title,
                    }
                    link_data.update(document_parent_object)
                    self.storage.parladata_api.links.set(link_data)

    def remove_leading_zeros(self, word, separeted_by=[',', '-', '/']):
        for separator in separeted_by:
            word = separator.join(map(lambda x: x.lstrip('0'), word.split(separator))).strip()
        return word


# OBRAVNAVA_PREDPISA -> KARTICA_FAZA_POSTOPKA
faze = [
    'Zakonodajni referendum',
    'druga obravnava - DZ',
    'druga obravnava - MDT',
    'druga obravnava DZ - nujni postopek',
    'druga obravnava DZ - skrajšani postopek',
    'druga obravnava MDT - nujni postopek',
    'druga obravnava MDT - skrajšani postopek',
    'konec postopka',
    'konec postopka - predstavitev',
    'konec postopka - seznanitev',
    'obravnava - DZ',
    'obravnava - MDT',
    'obravnava DZ - ratifikacija',
    'obravnava MDT - ratifikacija',
    'obravnava pobude',
    'obravnava postopka - nujni postopek',
    'obravnava postopka - skrajšani postopek',
    'prva faza',
    'prva obravnava',
    'sprejet predlog',
    'sprejet sklep',
    'tretja obravnava',
    'tretja obravnava - nujni postopek',
    'tretja obravnava - skrajšani postopek',
    'zahteva za ponovno odločanje'
]

# PREDPIS -> KARTICA_POSTOPEK
['sprejet predlog',
 'konec postopka']

# for faza in faze:
#     ProcedurePhase(
#         procedure_id=1,
#         name=faza
#     ).save()

