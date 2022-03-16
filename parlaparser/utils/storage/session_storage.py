from parlaparser.utils.parladata_api import ParladataApi


class Session(object):
    def __init__(self, name, gov_id, id, organizations, start_time, is_new, in_review) -> None:
        self.id = id
        self.name = name
        self.organizations = organizations
        self.count = None
        self.start_time = start_time
        self.gov_id = gov_id
        self.parladata_api = ParladataApi()
        self.is_new = is_new
        self.in_review = in_review

    def get_key(self) -> str:
        return self.gov_id.strip().lower()

    @classmethod
    def get_key_from_dict(ctl, data) -> str:
        return data['gov_id'].strip().lower()

    def get_speech_count(self):
        if self.count == None:
            self.count = self.parladata_api.get_speech_count(self.id)
        return self.count

    def unvalidate_speeches(self):
        self.parladata_api.unvalidate_speeches(self.id)

class SessionStorage(object):
    def __init__(self, core_storage) -> None:
        self.parladata_api = ParladataApi()
        self.sessions = {}
        self.dz_sessions_by_names = {}
        self.sessions_in_review = []
        self.storage = core_storage
        for session in self.parladata_api.get_sessions():
            temp_session = Session(
                name=session['name'],
                gov_id=session['gov_id'],
                id=session['id'],
                organizations = session['organizations'],
                start_time = session['start_time'],
                is_new=False,
                in_review=session['in_review']
            )
            self.sessions[temp_session.get_key()] = temp_session
            if temp_session.in_review:
                self.sessions_in_review.append(temp_session)

    def add_or_get_session(self, data) -> Session:
        key = Session.get_key_from_dict(data)
        if key in self.sessions.keys():
            return self.sessions[key]
        else:
            data.update(mandate=self.storage.mandate_id)
            session = self.parladata_api.set_session(data)
            new_session = Session(
                name=session['name'],
                gov_id=session['gov_id'],
                id=session['id'],
                organizations = session['organizations'],
                start_time = session['start_time'],
                is_new = True,
                in_review = session['in_review'],
            )
            self.sessions[new_session.get_key()] = new_session

            if new_session.in_review:
                self.sessions_in_review.append(new_session)

            if self.storage.main_org_id in new_session.organizations:
                self.dz_sessions_by_names[new_session.name.lower()] = new_session
            return new_session

    def patch_session(self, session, data):
        self.parladata_api.patch_session(session.id, data)

        # remove session from sessions_in_review if setted to in_review=False
        if not data.get('in_review', True):
            self.sessions_in_review.remove(session)

        # add session to sessions_in_review if setted to in_review=True
        if data.get('in_review', False):
            self.sessions_in_review.append(session)

    def is_session_in_review(self, session):
        return session in self.sessions_in_review
