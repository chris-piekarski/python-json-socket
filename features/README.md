Main lettuce repo still doesn't support python3
Use sgpy fork at https://github.com/sgpy/lettuce instead

Remove any existing python2/3 packages
pip uninstall lettuce
pip3 uninstall lettuce

Install fork version
git clone https://github.com/sgpy/lettuce
cd lettuce
python3 setup.py install

cd python-json-socket
lettuce
