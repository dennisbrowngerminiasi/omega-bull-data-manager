# shared_dict_manager.py
from multiprocessing.managers import BaseManager


class SharedDictManager(BaseManager):
    pass


def get_shared_dict(shared_dict):
    return shared_dict
