'''
a sketchy script that tries to recursively get info about an azure resource
MIT License - Charles Machalow
'''

import argparse
import dataclasses
import logging
import json
import subprocess
import typing

logger = logging.getLogger(__file__)

AzInfo = typing.TypeVar('AzInfo')
DictFuture = typing.TypeVar('DictFuture')
class AzInfo(dict):
    def __init__(self,
                 id_or_dict:typing.Union[str, dict],
                 id_to_dicts:typing.Optional[dict]=None):
        dict.__init__(self)

        if isinstance(id_or_dict, dict):
            self.id = id_or_dict['id']
            self.update(id_or_dict)
        else:
            self.id = id_or_dict

        # Share this dict with other AzInfo objects!
        self.id_to_dicts = id_to_dicts or {}

        raw = self._get_from_id_raw(self.id)
        if raw:
            self._add_nested_ids(raw)
            self._add_values_from_nesting(raw)
            if isinstance(raw, list):
                logger.debug("Coercing raw to a dict (was a list)")
                # force to a dict to call .update()
                raw = {'resources': raw}

            self.update(raw)

    def _add_nested_ids(self, obj):
        ''' keep track of what we already expanded... that way we won't expand to an infinite cycle '''

        if isinstance(obj, list):
            for idx, itm in enumerate(obj):
                self._add_nested_ids(itm)

        elif isinstance(obj, dict):
            if 'id' in obj and obj['id'] not in self.id_to_dicts:
                id = obj['id']
                self.id_to_dicts[id] = self._get_from_id_raw(id)
                self._add_nested_ids(self.id_to_dicts[id])

            for value in obj.values():
                self._add_nested_ids(value)

        return obj

    def _add_values_from_nesting(self, d:dict, id_to_dicts:dict=None):
        # it would be nice if instead of just removing id_to_dicts keys as we go,
        #  we created a placeholder/pointer.
        id_to_dicts = id_to_dicts or dict(self.id_to_dicts)

        if isinstance(d, list):
            for i in d:
                self._add_values_from_nesting(i, id_to_dicts)

        elif isinstance(d, dict):
            if 'id' in d:
                d.update(id_to_dicts.pop(d['id'], {}))

            for key, value in d.items():
                if isinstance(value, list):
                    for idx, itm in enumerate(value):
                        if isinstance(itm, dict):
                            self._add_values_from_nesting(itm, id_to_dicts)
                elif isinstance(value, dict):
                    self._add_values_from_nesting(value, id_to_dicts)
        else:
            logger.warning(f"Item: {d} of type {type(d)} was passed but not handled.")

    def _get_from_id_raw(self, id:str) -> typing.Optional[dict]:
        if id in self.id_to_dicts:
            logger.debug(f"Cache hit for id: {id}")
            return self.id_to_dicts[id]

        # We're getting this... if we need to get it again during this cycle (but before it is done getting), return a pointer
        logger.debug(f"Adding a future for id: {id} to cache")
        self.id_to_dicts[id] = DictFuture(id, self)

        query = f"""az graph query -q "Resources | where id == '{id}'" -o json"""
        if id.lower() == 'all':
            # 'special case for ALL resources
            query = f"""az graph query -q "Resources" -o json"""

        try:
            ret_val = json.loads(subprocess.check_output(query, shell=True))

            # if not getting all, grab first
            if id.lower() != 'all':
                ret_val = ret_val[0]
        except IndexError:
            ret_val = {}

        logger.debug(f"Adding ret_val to cache for id: {id}")
        self.id_to_dicts[id] = ret_val

        return ret_val

@dataclasses.dataclass
class DictFuture(dict):
    ''' Sort of like a pointer to avoid infinite recursion '''
    id:str
    parent_az_info:AzInfo

    def get(self) -> typing.Optional[AzInfo]:
        ''' Will attempt to get this object. '''
        return self.parent_az_info.id_to_dicts.get(self.id, None)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Will give all available info about a resource, as json. You should call az login to login before using this.')
    parser.add_argument('-i', '--id', type=str, help='The resource id to get info for. The string all can be given to pull all resources from this account.', required=True)
    parser.add_argument('-d', '--debug', action='store_true', help='If True, print debug info')
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, handlers=[logging.StreamHandler()])

    d = AzInfo(args.id)
    print(json.dumps(d, indent=4, sort_keys=True))

