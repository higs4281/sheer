import os
import sys
import codecs
import json
import logging
import copy
import urlparse

import requests

SPECIAL_DIRECTORIES = ['_defaults', '_queries', '_layouts', '_settings']


def read_json_file(path):
        if os.path.exists(path):
            with codecs.open(path, 'r','utf-8') as json_file:
                    return json.loads(json_file.read())

class Indexer(object):
    def __init__(self, path, name):
        self.path = path
        self.name = name

    def __str__(self):
        return "<{0}, {1}>".format(type(self).__name__, self.name)


class DirectoryIndexer(Indexer):
    
    def additional_mappings(self):
        mapping_path = os.path.join(self.path,'mappings.json')
        try:
            return read_json_file(mapping_path)

        except IOError:
            logging.debug("could not read %s" % mapping_path)

        except ValueError:
            logging.debug("could not parse JSON in %s" % mapping_path)

class FileIndexer(Indexer):
    pass

class PageIndexer(Indexer):
    name= "pages"

    def __init__(self):
        pages = []

    def add(self, path):
        self.pages.append(path)


def path_to_type_name(path):
    path=path.replace('/_', '_')
    path=path.replace('/', '_')
    path=path.replace('-','_')
    return path

def index_args(args):
    index_location(args.location, args.elasticsearch_index)

def index_location(path, es):
    requests.delete(es) #Lame, should refactor to use ES aliases
    settings_path = os.path.join(path,'_settings/settings.json')
    if os.path.exists(settings_path):
        requests.put(es, file(settings_path).read())
    else:
        requests.put(es)

    page_indexer = PageIndexer()
    indexers = [page_indexer]

    for root, dirs, files in os.walk(path):
        relative_root = root[len(path)+1:]
        for dir in dirs:
            relative_dir= '%s/%s' % (relative_root, dir)
            complete_dir= os.path.join(path, relative_dir)
            if dir.startswith('_') and dir not in SPECIAL_DIRECTORIES:
                indexer = DirectoryIndexer(complete_dir, path_to_type_name(relative_dir))
                indexers.append(indexer)

        for filename in files:
            complete_path=os.path.join(root, filename)
            basename, ext = os.path.splitext(filename)
            if filename.startswith('_'):
                path_no_ext= os.path.join(relative_root, basename)
                complete_path=os.path.join(root, filename)
                indexer= FileIndexer(complete_path, path_to_type_name(path_no_ext))
                indexers.append(indexer)

            elif ext.lower() in ['md','html']: 
                page_indexer.add(complete_path)
    if indexers:
        default_mapping_path = os.path.join(path, '_defaults/mappings.json')
        if os.path.exists(default_mapping_path):
            try:
                default_mapping = read_json_file(default_mapping_path)
            except ValueError:
                sys.exit("default mapping present, but is not valid JSON")

        else:
            default_mapping = {}

        for indexer in indexers:
            mappings = copy.deepcopy(default_mapping)
            if hasattr(indexer, 'additional_mappings'):
                additional_mappings = indexer.additional_mappings()
                if additional_mappings:
                    for key in additional_mappings.keys():
                        if key in mappings:
                            mappings[key].update(additional_mappings[key])
                        else:
                            mappings[key] = additional_mappings[key]
            index_url = urlparse.urljoin(es,indexer.name + '/_mapping')
            response = requests.put(index_url, json.dumps({indexer.name:mappings}))
            print "creating index for %s at %s [%s]" % (indexer.name, index_url, response.status_code)
            logging.debug(response.content)
    else:
        print "no indexable content found"