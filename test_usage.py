from app.usage_store import add_usage, get_usage
import pprint
add_usage("test-model", 10, 20)
usage = get_usage()
pprint.pprint(usage)
