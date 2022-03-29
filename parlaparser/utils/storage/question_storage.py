from parlaparser.utils.parladata_api import ParladataApi
from parlaparser.utils.storage.vote_storage import VoteStorage


class Question(object):
    def __init__(self, gov_id, id, is_new) -> None:
        self.parladata_api = ParladataApi()

        # question members
        self.id = id
        self.gov_id = gov_id
        self.is_new = is_new

    def get_key(self) -> str:
        return self.gov_id.strip().lower()

    @classmethod
    def get_key_from_dict(ctl, question) -> str:
        return question['gov_id'].strip().lower()


class QuestionStorage(object):
    def __init__(self, core_storage) -> None:
        self.parladata_api = ParladataApi()
        self.questions = {}
        self.storage = core_storage
    def load_data(self):
        if not self.questions:
            for question in self.parladata_api.get_questions():
                temp_question = Question(
                    gov_id=question['gov_id'],
                    id=question['id'],
                    is_new=False,
                )
                self.questions[temp_question.get_key()] = temp_question
            print(f'laoded was {len(self.questions)} questions')

    def add_or_get_session(self, data) -> Question:
        key = Question.get_key_from_dict(data)
        if key in self.questions.keys():
            return self.questions[key]
        else:
            data.update(mandate=self.storage.mandate_id)
            question = self.parladata_api.set_question(data)
            new_question = Question(
                gov_id=question['gov_id'],
                id=question['id'],
                is_new = True,
            )
            self.questions[new_question.get_key()] = new_question

            return new_question

    def set_question(self, data):
        added_question = self.parladata_api.set_question(data)
        return added_question

    def check_if_question_is_parsed(self, question):
        key = Question.get_key_from_dict(question)
        return key in self.questions.keys()

