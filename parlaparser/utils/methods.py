import requests
from tenacity import retry, stop_after_attempt, wait_chain, wait_fixed


@retry(
    stop=stop_after_attempt(4),
    wait=wait_chain(wait_fixed(10), wait_fixed(30), wait_fixed(60)),
    reraise=True,
)
def get_with_retry(url, **kwargs):
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return response


def get_values(data, key="UNID"):
    if isinstance(data, dict):
        children = data.get(key)
        return get_values(children, key)
    elif isinstance(data, list):
        output = [get_values(item, key) for item in data]
        if not output:
            return []
        if isinstance(output[0], list):
            return [item for sublist in output for item in sublist]
        return output
    elif isinstance(data, str):
        return [data]
    else:
        return []
