import requests
import xmltodict
import re
import locale

from datetime import datetime

from parlaparser.utils.methods import get_values


class QuestionParser(object):
    def __init__(self, storage):
        self.storage = storage
        self.question_storage = storage.question_parser
        self.question_storage.load_data()
        locale.setlocale(locale.LC_TIME, "sl_SI")
        self.documents = {}

    def load_documents(self, data):
        print('Loading documents')

        for doc in data['VPP']['DOKUMENT']:
            try:
                if 'PRIPONKA' in doc.keys():
                    urls = get_values(doc['PRIPONKA'], 'PRIPONKA_KLIC')
                    self.documents[doc['KARTICA_DOKUMENTA']['UNID']] = {
                        'title': doc['KARTICA_DOKUMENTA']['KARTICA_NASLOV'],
                        'urls': urls
                    }
            except:
                print(doc)
                raise Exception('key_error')
        self.document_keys = self.documents.keys()

    def parse(self):
        url = f'https://fotogalerija.dz-rs.si/datoteke/opendata/VPP.XML'
        response = requests.get(url)
        with open(f'/tmp/VPP.XML', 'wb') as f:
            f.write(response.content)
        with open('/tmp/VPP.XML', 'rb') as data_file:
            data = xmltodict.parse(data_file, dict_constructor=dict)

        # load documents from XML
        self.load_documents(data)

        for question in data['VPP']['VPRASANJE']:

            question_card = question['KARTICA_VPRASANJA']
            question_documents = question.get('PODDOKUMENTI', [])
            document_unids = get_values(question_documents)

            authors = question_card['KARTICA_VLAGATELJ']
            date = question_card['KARTICA_DATUM']
            title = question_card['KARTICA_NASLOV']
            recipient_text = question_card['KARTICA_NASLOVLJENEC']
            question_type_text = question_card['KARTICA_VRSTA']
            question_unid = question_card['UNID']
            timestamp = datetime.strptime(date, '%Y-%m-%d')

            if question_type_text == 'PP':
                question_type = 'initiative'
            elif question_type_text == 'PPV':
                question_type = 'question'
            elif question_type_text == 'UPV':
                question_type = 'question'
            else:
                raise Exception(f'Unkonwn question type: {question_type_text}')

            question_data = {
                'title': title,
                'recipient_text': recipient_text,
                'type_of_question': question_type,
                'timestamp': timestamp.isoformat(),
                'gov_id': question_unid
            }
            if self.question_storage.check_if_question_is_parsed(question_data):
                print('question is alredy parsed')
                continue

            print(f'{authors}: {title}')

            if isinstance(authors, list):
                pass
            else:
                authors = [authors]

            people_ids = []
            for author in authors:
                person = self.storage.people_storage.get_or_add_person(
                    author,
                )
                people_ids.append(person.id)

            question_data.update({
                'person_authors': people_ids
                }
            )

            question = self.question_storage.set_question(question_data)

            question_id = question['id']

            for doc_unid in document_unids:
                if doc_unid in self.document_keys:
                    document = self.documents[doc_unid]
                    doc_title = document['title']
                    for doc_url in document['urls']:
                        link_data = {
                            'question': question_id,
                            'url': doc_url,
                            'name': doc_title,
                        }
                        self.storage.set_link(link_data)
