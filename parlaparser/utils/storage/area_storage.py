from parlaparser.utils.parladata_api import ParladataApi


class Area(object):
    def __init__(self, name, id, is_new) -> None:
        self.parladata_api = ParladataApi()

        # session members
        self.id = id
        self.name = name

    def get_key(self) -> str:
        return (self.name).strip().lower()

    @classmethod
    def get_key_from_dict(ctl, area) -> str:
        return (area['name']).strip().lower()


class AreaStorage(object):
    def __init__(self, core_storage) -> None:
        self.parladata_api = ParladataApi()
        self.areas = {}
        self.storage = core_storage
        for area in self.parladata_api.get_areas():
            self.store_area(area, is_new=False)

    def store_area(self, area, is_new) -> Area:
        temp_area = Area(
            name=area['name'],
            id=area['id'],
            is_new=is_new,
        )
        self.areas[temp_area.get_key()] = temp_area
        return temp_area

    def get_or_add_area(self, data) -> Area:
        key = Area.get_key_from_dict(data)
        if key in self.areas.keys():
            area = self.areas[key]
        else:
            area = self.parladata_api.set_area(data)
            area = self.store_area(area, is_new=True)
        return area



