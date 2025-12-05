from erc3 import Erc3Client
from erc3.erc3 import Req_ListWiki, Resp_ListWiki, Resp_LoadWiki, Req_LoadWiki
import os

def _save_file(base_path, file_path, content):
    full_path = os.path.join(base_path, file_path)

    # Create parent directories if they don't exist
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    # Write the content to the file
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

def dump_wiki(erc3_api: Erc3Client, base_path: str):
    list_wiki_result : Resp_ListWiki = erc3_api.dispatch(Req_ListWiki())
    for path in list_wiki_result.paths:
        wiki_file_result : Resp_LoadWiki = erc3_api.dispatch(Req_LoadWiki(file=path))
        _save_file(base_path, file_path=wiki_file_result.file, content=wiki_file_result.content)
