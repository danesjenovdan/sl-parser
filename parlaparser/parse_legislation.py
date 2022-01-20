import requests
import xmltodict
import re
import locale

from datetime import datetime

from lxml import html
from enum import Enum

from parlaparser.settings import BASE_URL
from parlaparser.utils.methods import get_values


class LegislationParser(object):
    def __init__(self, storage):
        self.storage = storage
        locale.setlocale(locale.LC_TIME, "sl_SI")
        self.documents = {}

    def load_documents(self, data, key='PZ'):
        print('Loading documents')

        for doc in data[key]['DOKUMENT']:
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
        self.mandate = 'VIII'
        urls = [
            # {
            #     'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/PZ.XML',
            #     'type': 'legislation',
            #     'file_name': 'PZ.XML',
            #     'xml_key': 'PZ',
            # },
            {
                'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/PZ8.XML',
                'type': 'legislation',
                'file_name': 'PZ8.XML',
                'xml_key': 'PZ',
            },
            {
                'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/PA.XML',
                'type': 'act',
                'file_name': 'PA.XML',
                'xml_key': 'PA',
            },
            # {
            #     'url': 'https://fotogalerija.dz-rs.si/datoteke/opendata/SA.XML',
            #     'type': 'act',
            #     'file_name': 'SA.XML',
            #     'xml_key': 'SA',
            # }
        ]
        for legislation_file in urls:
            print('parse file: ', legislation_file["file_name"])
            response = requests.get(legislation_file['url'])
            with open(f'parlaparser/files/{legislation_file["file_name"]}', 'wb') as f:
                f.write(response.content)
            with open(f'parlaparser/files/{legislation_file["file_name"]}', 'rb') as data_file:
                data = xmltodict.parse(data_file, dict_constructor=dict)

            # load documents from XML
            self.load_documents(data, legislation_file['xml_key'])
            self.parse_xml_data(data, legislation_file, array_key='PREDPIS', obj_key='KARTICA_PREDPISA')
            self.parse_xml_data(data, legislation_file, array_key='OBRAVNAVA_PREDPISA', obj_key='KARTICA_OBRAVNAVE_PREDPISA')


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
        except:
            print(legislation_file)
            print(data.keys())
            raise Exception()
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
                if date:
                    date_iso = datetime.strptime(date, '%Y-%m-%d').isoformat()
                else:
                    date_iso = None

                legislation_documents = wraped_legislation.get('PODDOKUMENTI', [])
                document_unids = get_values(legislation_documents)

                connected_legislation = wraped_legislation.get('POVEZANI_PREDPISI', [])
                connected_legislation_unids = get_values(connected_legislation)
            except Exception as e:
                print(legislation)
                print(e)
                continue

            if array_key == 'PREDPIS': # legislation
                self.add_or_update_legislation(
                    {
                        'text': title,
                        'epa': epa,
                        'uid': unid,
                        'timestamp': date_iso,
                        'classification': self.storage.legislation_classifications.get(legislation_file['type'], None)
                    },
                    document_unids
                )
            else: # legislation consideration
                self.set_legislation_consideration(
                    {
                        'epa': epa,
                        'uid': unid,
                        'organization': champion_wb,
                        'timestamp': date_iso,
                        'consideration_phase': legislation_procedure_phase
                    },
                    document_unids
                )

    def set_legislation_consideration(self, legislation_consideration, document_unids):
        epa = legislation_consideration['epa']
        if epa in self.storage.legislation.keys():
            legislation_id = self.storage.legislation[epa]['id']

            procedure_phase_id = self.storage.procedure_phases[legislation_consideration.pop('consideration_phase')]['id']
            organization_name = legislation_consideration['organization']

            if organization_name:
                organization_id, added = self.storage.get_or_add_organization(
                    organization_name,
                    {
                        'name': organization_name,
                        'parser_names': organization_name,
                    },
                )
            else:
                organization_id = None
            legislation_consideration.update({
                'organization': organization_id,
                'procedure_phase': procedure_phase_id,
                'legislation': legislation_id
            })

            legislation_consideration_key = self.storage.get_legislation_consideration_key(legislation_consideration)
            if not legislation_consideration_key in self.storage.legislation_considerations.keys():
                legislation_consideration_obj = self.storage.set_legislation_consideration(
                    legislation_consideration
                )
                self.add_docs(document_unids, {'legislation_consideration': legislation_consideration_obj['id']})
                # when patch don't add documents...


    def add_or_update_legislation(self, legislation_obj, document_unids):
        epa = legislation_obj['epa']
        if epa in self.storage.legislation.keys():
            legislation_obj.pop('epa')
            if self.storage.legislation[epa]['text']:
                pass
                # legislation already exists with text
            else:
                print('nima texta')
                legislation_id = self.storage.legislation[epa]['id']

                self.storage.patch_legislation(
                    legislation_id,
                    legislation_obj
                )
                # when patch don't add documents...
        else:
            legislation_obj = self.storage.set_legislation(
                legislation_obj
            )
            self.add_docs(document_unids, {'legislation': legislation_obj['id']})


    def add_docs(self, document_unids, document_parent_object):
        print(document_unids)
        if not document_unids:
            return
        for doc_unid in document_unids:
            if doc_unid in self.document_keys:
                document = self.documents[doc_unid]
                doc_title = document['title']
                print(document['urls'])
                for doc_url in document['urls']:
                    link_data = {
                        'url': doc_url,
                        'name': doc_title,
                    }
                    link_data.update(document_parent_object)
                    self.storage.set_link(link_data)

    def remove_leading_zeros(self, word, separeted_by=[',', '-', '/']):
        for separator in separeted_by:
            word = separator.join(map(lambda x: x.lstrip('0'), word.split(separator)))
        return word


# OBRAVNAVA_PREDPISA -> KARTICA_FAZA_POSTOPKA
faze = ['Zakonodajni referendum',
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
    'zahteva za ponovno odločanje']

# PREDPIS -> KARTICA_POSTOPEK
['sprejet predlog',
 'konec postopka']

# for faza in faze:
#     ProcedurePhase(
#         procedure_id=1,
#         name=faza
#     ).save()

