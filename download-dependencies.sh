export LIB_DIRECTORY=./lib/python/
rm -rf "$LIB_DIRECTORY"
mkdir -p "$LIB_DIRECTORY"

pip install -t "$LIB_DIRECTORY" -r requirements.lock
