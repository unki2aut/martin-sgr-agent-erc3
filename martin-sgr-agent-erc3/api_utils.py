# list all projects as the search API is not so helpful
def list_projects(store_api, offset: int = 0, limit: int = 5):
    projects = []

    resp = store_api.list_projects(limit=limit, offset=offset)

    while resp.next_offset > 0:
        projects.extend([project.dict() for project in resp.projects])
        offset = resp.next_offset
        resp = store_api.list_projects(limit=limit, offset=offset)

    return projects
