from parlaparser.utils.parladata_api import ParladataApi


class AgendaItem(object):
    def __init__(self, name, id, datetime, is_new) -> None:
        self.parladata_api = ParladataApi()

        # session members
        self.id = id
        self.name = name
        self.datetime = datetime
        self.is_new = is_new

    def get_key(self) -> str:
        return (self.name + '_' + self.datetime).strip().lower()

    @classmethod
    def get_key_from_dict(ctl, agenda_item) -> str:
        return (agenda_item['name'] + '_' + agenda_item['datetime']).strip().lower()


class AgendaItemStorage(object):
    def __init__(self, core_storage) -> None:
        self.parladata_api = ParladataApi()
        self.agenda_items = {}
        self.storage = core_storage
        for agenda_item in self.parladata_api.get_agenda_items():
            self.store_agenda_item(agenda_item, is_new=False)

    def store_agenda_item(self, agenda_item, is_new) -> AgendaItem:
        temp_agenda_item = AgendaItem(
            name=agenda_item['name'],
            datetime = agenda_item['datetime'],
            id=agenda_item['id'],
            is_new=is_new,
        )
        self.agenda_items[temp_agenda_item.get_key()] = temp_agenda_item
        return temp_agenda_item

    def get_or_add_agenda_item(self, data,) -> AgendaItem:
        key = AgendaItem.get_key_from_dict(data)
        if key in self.agenda_items.keys():
            agenda_item = self.agenda_items[key]
        else:
            added_agenda_item = self.parladata_api.set_agenda_item(data)
            agenda_item = self.store_agenda_item(added_agenda_item, is_new=True)
        return agenda_item



