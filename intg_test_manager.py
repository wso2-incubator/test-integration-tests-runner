# Copyright (c) 2018, WSO2 Inc. (http://wso2.com) All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# importing required modules
import glob
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile
import subprocess
import wget
import logging
import inspect
import os
import shutil
import pymysql
import sqlparse
import stat
import re
import os.path
import getpass
import fnmatch
from pathlib import Path
import urllib.request as urllib2
from xml.dom import minidom
import errno
from subprocess import Popen, PIPE

from intg_test_constant import DEPLOYMENT_PROPERTY_FILE_NAME, LOG_FILE_NAME, \
    PRODUCT_STORAGE_DIR_NAME, DEFAULT_DB_USERNAME, LOG_STORAGE, NS, ZIP_FILE_EXTENSION, TEST_OUTPUT_DIR_NAME, \
    SURFACE_PLUGIN_ARTIFACT_ID, CARBON_NAME, VALUE_TAG, DEFAULT_ORACLE_SID, MYSQL_DB_ENGINE, \
    ORACLE_DB_ENGINE, MSSQL_DB_ENGINE


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class ZipFileLongPaths(ZipFile):
    def _extract_member(self, member, targetpath, pwd):
        targetpath = winapi_path(targetpath)
        return ZipFile._extract_member(self, member, targetpath, pwd)


def winapi_path(dos_path, encoding=None):
    path = os.path.abspath(dos_path)

    if path.startswith("\\\\"):
        path = "\\\\?\\UNC\\" + path[2:]
    else:
        path = "\\\\?\\" + path

    return path


def on_rm_error(func, path, exc_info):
    os.chmod(path, stat.S_IWRITE)
    os.unlink(path)


git_repo_url = None
git_branch = None
os_type = None
workspace = None
dist_name = None
dist_zip_name = None
product_id = None
log_file_name = None
target_path = None
db_engine = None
db_engine_version = None
latest_product_release_api = None
latest_product_build_artifacts_api = None
sql_driver_location = None
db_host = None
db_port = None
db_username = None
db_password = None
tag_name = None
test_mode = None
product_version = None
wum_product_version = None
database_config = {}
storage_dir_abs_path = None
use_custom_testng_file=None
githubsshkey=None
sshKeyvalue=None


def read_property_files():
    global db_engine
    global db_engine_version
    global git_repo_url
    global git_branch
    global latest_product_release_api
    global latest_product_build_artifacts_api
    global sql_driver_location
    global db_host
    global db_port
    global db_username
    global db_password
    global workspace
    global product_id
    global database_config
    global test_mode
    global wum_product_version
    global use_custom_testng_file
    global githubsshkey
    global sshKeyvalue


    workspace = os.getcwd()
    property_file_paths = []
    deployment_prop_path = Path(workspace + "/" + DEPLOYMENT_PROPERTY_FILE_NAME)

    if Path.exists(deployment_prop_path):
        property_file_paths.append(deployment_prop_path)

        for path in property_file_paths:
            with open(path, 'r') as filehandle:
                for line in filehandle:
                    if line.startswith("#"):
                        continue
                    prop = line.split("=")
                    key = prop[0]
                    val = prop[1]
                    if key == "DBEngine":
                        db_engine = val.strip()
                    elif key == "DBEngineVersion":
                        db_engine_version = val
                    elif key == "PRODUCT_GIT_URL":
                        git_repo_url = val.strip().replace('\\', '')
                        product_id = git_repo_url.split("/")[-1].split('.')[0]
                    elif key == "PRODUCT_GIT_BRANCH":
                        git_branch = val.strip()
                    elif key == "LATEST_PRODUCT_RELEASE_API":
                        latest_product_release_api = val.strip().replace('\\', '')
                    elif key == "LATEST_PRODUCT_BUILD_ARTIFACTS_API":
                        latest_product_build_artifacts_api = val.strip().replace('\\', '')
                    elif key == "SQL_DRIVERS_LOCATION_UNIX" and not sys.platform.startswith('win'):
                        sql_driver_location = val.strip()
                    elif key == "SQL_DRIVERS_LOCATION_WINDOWS" and sys.platform.startswith('win'):
                        sql_driver_location = val.strip()
                    elif key == "DatabaseHost":
                        db_host = val.strip()
                    elif key == "DatabasePort":
                        db_port = val.strip()
                    elif key == "DBUsername":
                        db_username = val.strip()
                    elif key == "DBPassword":
                        db_password = val.strip()
                    elif key == "TEST_MODE":
                        test_mode = val.strip()
                    elif key == "WUM_PRODUCT_VERSION":
                        wum_product_version = val.strip()
                    elif key == "USE_CUSTOM_TESTNG":
                        use_custom_testng_file = val.strip()
                    elif key == "githubSshKey":
                        githubsshkey = val.strip()
                        # ssh-key arrange with the correct key format.
                        keystart = "-----BEGIN RSA PRIVATE KEY-----"
                        keyend = "-----END RSA PRIVATE KEY-----"
                        githubKeyStripStart =  githubsshkey.split(keystart,1)[1]
                        githubKeyStripStart =  githubKeyStripStart.split(keyend,1)[0]
                        replaced_key = githubKeyStripStart.replace(' ', '\n')
                        # remove the new line character at the start of the string replaced_key
                        sshKey = replaced_key[1:]
                        # append padding
                        sshKeyvalue = keystart + "\n" + sshKey + "==\n" + keyend
    else:
        raise Exception("Test Plan Property file or Infra Property file is not in the workspace: " + workspace)


def validate_property_readings():
    missing_values = ""
    if db_engine is None:
        missing_values += " -DBEngine- "
    if git_repo_url is None:
        missing_values += " -PRODUCT_GIT_URL- "
    if product_id is None:
        missing_values += " -product-id- "
    if git_branch is None:
        missing_values += " -PRODUCT_GIT_BRANCH- "
    if latest_product_release_api is None:
        missing_values += " -LATEST_PRODUCT_RELEASE_API- "
    if latest_product_build_artifacts_api is None:
        missing_values += " -LATEST_PRODUCT_BUILD_ARTIFACTS_API- "
    if sql_driver_location is None:
        missing_values += " -SQL_DRIVERS_LOCATION_<OS_Type>- "
    if db_host is None:
        missing_values += " -DatabaseHost- "
    if db_port is None:
        missing_values += " -DatabasePort- "
    if db_password is None:
        missing_values += " -DBPassword- "
    if test_mode is None:
        missing_values += " -TEST_MODE- "
    if wum_product_version is None:
        missing_values += " -WUM_PRODUCT_VERSION- "
    if use_custom_testng_file is None:
        missing_values += " -USE_CUSTOM_TESTNG- "
    if githubsshkey is None:
        missing_values += " -githubSshKey- "

    if missing_values != "":
        logger.error('Invalid property file is found. Missing values: %s ', missing_values)
        return False
    else:
        return True


def construct_url(prefix):
    url = prefix + db_host + ":" + db_port
    return url


def function_logger(file_level, console_level=None):
    global log_file_name
    log_file_name = LOG_FILE_NAME
    function_name = inspect.stack()[1][3]
    logger = logging.getLogger(function_name)
    # By default, logs all messages
    logger.setLevel(logging.DEBUG)

    if console_level != None:
        # StreamHandler logs to console
        ch = logging.StreamHandler()
        ch.setLevel(console_level)
        ch_format = logging.Formatter('%(asctime)s - %(message)s')
        ch.setFormatter(ch_format)
        logger.addHandler(ch)

    # log in to a file
    fh = logging.FileHandler("{0}.log".format(function_name))
    fh.setLevel(file_level)
    fh_format = logging.Formatter('%(asctime)s - %(lineno)d - %(levelname)-8s - %(message)s')
    fh.setFormatter(fh_format)
    logger.addHandler(fh)

    return logger


def download_file(url, destination):
    """Download a file using wget package.
    Download the given file in _url_ as the directory+name provided in _destination_
    """
    wget.download(url, destination)


def get_db_hostname(url, db_type):
    """Retreive db hostname from jdbc url
    """
    if db_type == 'ORACLE':
        hostname = url.split(':')[3].replace("@", "")
    else:
        hostname = url.split(':')[2].replace("//", "")
    return hostname


def run_sqlserver_commands(query):
    """Run SQL_SERVER commands using sqlcmd utility.
    """
    subprocess.call(
        ['sqlcmd', '-S', db_host, '-U', database_config['user'], '-P', database_config['password'], '-Q', query])


def get_mysql_connection(db_name=None):
    if db_name is not None:
        conn = pymysql.connect(host=get_db_hostname(database_config['url'], 'MYSQL'), user=database_config['user'],
                               passwd=database_config['password'], db=db_name)
    else:
        conn = pymysql.connect(host=get_db_hostname(database_config['url'], 'MYSQL'), user=database_config['user'],
                               passwd=database_config['password'])
    return conn


def run_mysql_commands(query):
    """Run mysql commands using mysql client when db name not provided.
    """
    conn = get_mysql_connection()
    conectr = conn.cursor()
    conectr.execute(query)
    conn.close()


def get_ora_user_carete_query(database):
    query = "CREATE USER {0} IDENTIFIED BY {1};".format(
        database, database_config["password"])
    return query


def get_ora_grant_query(database):
    query = "GRANT CONNECT, RESOURCE, DBA TO {0};".format(
        database)
    return query


def execute_oracle_command(query):
    """Run oracle commands using sqlplus client when db name(user) is not provided.
    """
    connect_string = "{0}/{1}@//{2}/{3}".format(database_config["user"], database_config["password"],
                                                db_host, "ORCL")
    session = Popen(['sqlplus', '-S', connect_string], stdin=PIPE, stdout=PIPE, stderr=PIPE)
    session.stdin.write(bytes(query, 'utf-8'))
    return session.communicate()


def create_oracle_user(database):
    """This method is able to create the user and grant permission to the created user in oracle
    """
    user_creating_query = get_ora_user_carete_query(database)
    logger.info("")
    logger.info(execute_oracle_command(user_creating_query))
    permission_granting_query = get_ora_grant_query(database)
    return execute_oracle_command(permission_granting_query)


def run_oracle_script(script, database):
    """Run oracle commands using sqlplus client when dbname(user) is provided.
    """
    connect_string = "{0}/{1}@//{2}/{3}".format(database, database_config["password"],
                                                db_host, "ORCL")
    session = Popen(['sqlplus', '-S', connect_string], stdin=PIPE, stdout=PIPE, stderr=PIPE)
    session.stdin.write(bytes(script, 'utf-8'))
    return session.communicate()


def run_sqlserver_script_file(db_name, script_path):
    """Run SQL_SERVER script file on a provided database.
    """
    subprocess.call(
        ['sqlcmd', '-S', db_host, '-U', database_config["user"], '-P', database_config["password"], '-d', db_name, '-i',
         script_path])


def run_mysql_script_file(db_name, script_path):
    """Run MYSQL db script file on a provided database.
    """
    conn = get_mysql_connection(db_name)
    connector = conn.cursor()

    sql = open(script_path).read()
    sql_parts = sqlparse.split(sql)
    for sql_part in sql_parts:
        if sql_part.strip() == '':
            continue
        connector.execute(sql_part)
    conn.commit()
    conn.close()


def ignore_dirs(directories):
    """
        Define the ignore pattern for copytree.
    """
    def _ignore_patterns(path, names):
        ignored_names = []
        for directory in directories:
            ignored_names.extend(fnmatch.filter(names, directory))
        return set(ignored_names)
    return _ignore_patterns


def get_dist_name(path):
    """Get the product name by reading distribution pom.
    """
    global dist_name
    global dist_zip_name
    global product_version

    dist_pom_path = Path(workspace + "/" + product_id + "/" + path)
    if sys.platform.startswith('win'):
        dist_pom_path = winapi_path(dist_pom_path)
    ET.register_namespace('', NS['d'])
    artifact_tree = ET.parse(dist_pom_path)
    artifact_root = artifact_tree.getroot()
    parent = artifact_root.find('d:parent', NS)
    artifact_id = artifact_root.find('d:artifactId', NS).text
    product_version = parent.find('d:version', NS).text
    dist_name = artifact_id + "-" + product_version
    dist_zip_name = dist_name + ZIP_FILE_EXTENSION
    return dist_name


def get_dist_name_wum():
    global dist_name
    global dist_zip_name
    global product_version

    os.chdir(PRODUCT_STORAGE_DIR_NAME)
    product_version=wum_product_version
    #name = glob.glob('*-' + product_version)[0]
    name = glob.glob('*.zip')[0]
    dist_name = os.path.splitext(name)[0]
    logger.info("wum dist_name: " + dist_name)
    return dist_name


def setup_databases(db_names, meta_data):
    """Create required databases.
    """
    base_path = Path(workspace + "/" + PRODUCT_STORAGE_DIR_NAME + "/" + dist_name + "/" )
    engine = db_engine.upper()
    db_meta_data = meta_data
    if db_meta_data:
        databases = db_meta_data["DB_SETUP"]
        if databases:
            for db_name in db_names:
                db_scripts = databases[db_name]
                if len(db_scripts) == 0:
                    if engine == 'SQLSERVER-SE':
                        # create database for MsSQL
                        run_sqlserver_commands('CREATE DATABASE {0}'.format(db_name))
                    elif engine == 'MYSQL':
                        # create database for MySQL
                        run_mysql_commands('CREATE DATABASE IF NOT EXISTS {0};'.format(db_name))
                    elif engine == 'ORACLE-SE2':
                        # create database for Oracle
                        create_oracle_user(db_name)
                else:
                    if engine == 'SQLSERVER-SE':
                        # create database for MsSQL
                        run_sqlserver_commands('CREATE DATABASE {0}'.format(db_name))
                        for db_script in db_scripts:
                            path = base_path / db_script
                            # run db scripts
                            run_sqlserver_script_file(db_name, str(path))
                    elif engine == 'MYSQL':
                        # create database for MySQL
                        run_mysql_commands('CREATE DATABASE IF NOT EXISTS {0};'.format(db_name))
                        # run db scripts
                        for db_script in db_scripts:
                            path = base_path / db_script
                            run_mysql_script_file(db_name, str(path))
                    elif engine == 'ORACLE-SE2':
                        # create oracle schema
                        create_oracle_user(db_name)
                        # run db script
                        for db_script in db_scripts:
                            path = base_path / db_script
                            run_oracle_script('@{0}'.format(str(path)), db_name)
            logger.info('Database setting up is done.')
        else:
            raise Exception("Database setup configuration is not defined in the constant file")
    else:
        raise Exception("Database meta data is not defined in the constant file")


def construct_db_config(meta_data):
    """Use properties which are get by reading property files and construct the database config object which will use
    when configuring the databases.
    """
    db_meta_data = meta_data
    if db_meta_data:
        database_config["driver_class_name"] = db_meta_data["driverClassName"]
        database_config["password"] = db_password
        database_config["sql_driver_location"] = sql_driver_location + "/" + db_meta_data["jarName"]
        database_config["url"] = construct_url(db_meta_data["prefix"])
        database_config["db_engine"] = db_engine
        if db_username is None:
            database_config["user"] = DEFAULT_DB_USERNAME
        else:
            database_config["user"] = db_username

    else:
        raise BaseException(
            "DB config parsing is failed. DB engine name in the property file doesn't match with the constant: " + str(
                db_engine.upper()))


def build_module(module_path):
    """Build a given module.
    """
    logger.info('Start building a module. Module: ' + str(module_path))
    if sys.platform.startswith('win'):
        subprocess.call(['mvn', 'clean', 'install', '-fae', '-B',
                         '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn'],
                        shell=True, cwd=module_path)
    else:
        subprocess.call(['mvn', 'clean', 'install', '-fae', '-B',
                         '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn'],
                        cwd=module_path)
    logger.info('Module build is completed. Module: ' + str(module_path))

def build_module_support(module_path):
    """Build a given module.
    """
    if sys.platform.startswith('win'):
        logger.info('Start building Module: ' + str(module_path))
        subprocess.call(['mvn', '--settings', 'uat-nexus-settings.xml', 'clean', 'install', '-fae', '-B',
                         '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn'],
                        shell=True, cwd=module_path)
    else:
        logger.info('Start building Module: ' + str(module_path))
        subprocess.call(['mvn', '--settings', 'uat-nexus-settings.xml', 'clean', 'install', '-fae', '-B',
                         '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn'],
                        cwd=module_path)
    logger.info('Module build is completed with nexus. Module: ' + str(module_path))

def clone_repo():
    """Clone the product repo
    """
    logger.info('Cloning the repo: Initiation')
    try:
        if test_mode == "WUM":
            subprocess.call(['bash', 'clone_product_repo_wum.sh', sshKeyvalue, git_branch, git_repo_url])
        else:
            subprocess.call(['git', 'clone', '--branch', git_branch, git_repo_url], cwd=workspace)
            logger.info('product repository cloning is done.')
    except Exception as e:
        logger.error("Error occurred while cloning the product repo: ", exc_info=True)



def get_latest_tag_name():
    """Get the latest tag name from git location
    """
    global tag_name
    git_path = Path(workspace + "/" + product_id)
    binary_val_of_tag_name = subprocess.Popen(["git", "describe", "--abbrev=0", "--tags"],
                                              stdout=subprocess.PIPE, cwd=git_path)
    tag_name = binary_val_of_tag_name.stdout.read().strip().decode("utf-8")
    return tag_name


def checkout_to_tag():
    """Checkout to the given tag
    """
    try:
        git_path = Path(workspace + "/" + product_id)
        name = get_latest_tag_name()
        tag = "tags/" + name
        subprocess.call(["git", "fetch", "origin", tag], cwd=git_path)
        subprocess.call(["git", "checkout", "-B", tag, name], cwd=git_path)
        logger.info('checkout to the branch: ' + tag)
    except Exception as e:
        logger.error("Error occurred while cloning the product repo and checkout to the latest tag of the branch",
                     exc_info=True)


def get_product_file_path():
    """Get the absolute path of the distribution which is located in the storage directory
    """
    # product download path and file name constructing
    product_download_dir = Path(workspace + "/" + PRODUCT_STORAGE_DIR_NAME)
    if not Path.exists(product_download_dir):
        Path(product_download_dir).mkdir(parents=True, exist_ok=True)
    return product_download_dir / dist_zip_name


def get_relative_path_of_dist_storage(xml_path):
    """Get the relative path of distribution storage
    """
    dom = minidom.parse(urllib2.urlopen(xml_path))  # parse the data
    artifact_elements = dom.getElementsByTagName('artifact')

    for artifact in artifact_elements:
        file_name_elements = artifact.getElementsByTagName("fileName")
        for file_name in file_name_elements:
            if file_name.firstChild.nodeValue == dist_zip_name:
                parent_node = file_name.parentNode
                return parent_node.getElementsByTagName("relativePath")[0].firstChild.nodeValue
    return None


def get_latest_released_dist():
    """Get the latest released distribution
    """
    # construct the distribution downloading url
    relative_path = get_relative_path_of_dist_storage(latest_product_release_api + "xml")
    if relative_path is None:
        raise Exception("Error occured while getting relative path")
    dist_downl_url = latest_product_release_api.split('/api')[0] + "/artifact/" + relative_path
    # download the last released pack from Jenkins
    download_file(dist_downl_url, str(get_product_file_path()))
    logger.info("product-file-path = : " + str(get_product_file_path()))
    logger.info('downloading the latest released pack from Jenkins is completed.')


def get_latest_stable_artifacts_api():
    """Get the API of the latest stable artifactsF
    """
    dom = minidom.parse(urllib2.urlopen(latest_product_build_artifacts_api + "xml"))
    main_artifact_elements = dom.getElementsByTagName('mainArtifact')

    for main_artifact in main_artifact_elements:
        canonical_name_elements = main_artifact.getElementsByTagName("canonicalName")
        for canonical_name in canonical_name_elements:
            if canonical_name.firstChild.nodeValue == dist_name + ".pom":
                parent_node = main_artifact.parentNode
                return parent_node.getElementsByTagName("url")[0].firstChild.nodeValue
    return None


def get_latest_stable_dist():
    """Download the latest stable distribution
    """
    build_num_artifact = get_latest_stable_artifacts_api()
    build_num_artifact = re.sub(r'http.//(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})', "https://wso2.org", str(build_num_artifact))
    if build_num_artifact is None:
        raise Exception("Error occured while getting latest stable build artifact API path")
    relative_path = get_relative_path_of_dist_storage(build_num_artifact + "api/xml")
    if relative_path is None:
        raise Exception("Error occured while getting relative path")
    dist_downl_url = build_num_artifact + "artifact/" + relative_path
    download_file(dist_downl_url, str(get_product_file_path()))
    logger.info('downloading the latest stable pack from Jenkins is completed.')


def create_output_property_fle():
    """Create output property file which is used when generating email
    """
    output_property_file = open("output.properties", "w+")
    if test_mode == "WUM":
        logger.info("PRODUCT GIT URL: " + git_repo_url)
        # temporally fix. Needs to be change.get the git url without username and the password
        head, sep, tail = git_repo_url.partition('//')
        uri=head
        head, sep, tail = git_repo_url.partition('@')
        urn=tail
        git_url=uri+"//"+urn
        git_url = git_url + "/tree/" + git_branch
        logger.info("GIT URL: " + git_url)
        output_property_file.write("GIT_LOCATION=%s\r\n" % git_url)
        output_property_file.write("GIT_REVISION=%s\r\n" % git_branch)
    else:
        git_url = git_repo_url + "/tree/" + git_branch
        output_property_file.write("GIT_LOCATION=%s\r\n" % git_url)
        output_property_file.write("GIT_REVISION=%s\r\n" % tag_name)
    output_property_file.close()


def replace_file(source, destination):
    """Replace source file to the destination
    """
    logger.info('Replacing files from:' + str(source) + " to: " + str(destination))
    if sys.platform.startswith('win'):
        source = winapi_path(source)
        destination = winapi_path(destination)
    shutil.move(source, destination)


def extract_product(dir_path, zip_path ):
    """Extract the zip file(product zip) which is located in the given @path.
    """
    storage_dir_abs_path = dir_path
    storage_zip_abs_path = zip_path
    if Path.exists(storage_zip_abs_path):
        logger.info("Extracting the product  into " + str(storage_dir_abs_path))
        if sys.platform.startswith('win'):
            with ZipFileLongPaths(storage_zip_abs_path, "r") as zip_ref:
                zip_ref.extractall(storage_dir_abs_path)
        else:
            with ZipFile(str(storage_zip_abs_path), "r") as zip_ref:
                zip_ref.extractall(storage_dir_abs_path)
    else:
        raise FileNotFoundError("File is not found to extract, file path: " + str(storage_zip_abs_path))


def attach_jolokia_agent(spath):
    logger.info('attaching jolokia agent as a java agent')
    sp = str(spath)

    if sys.platform.startswith('win'):
        sp = sp + ".bat"
        if Path.exists(Path(sp)):
            jolokia_agent = \
                "-javaagent:C:\\testgrid\\jolokia-jvm-1.6.0-agent.jar=port=8778,host=localhost,protocol=http "
            with open(sp, "r") as in_file:
                buf = in_file.readlines()
            with open(sp, "w") as out_file:
                for line in buf:
                    if line.startswith("set CMD_LINE_ARGS"):
                        newline = str(line).replace("CMD_LINE_ARGS=", 'CMD_LINE_ARGS=' + jolokia_agent)
                        line = newline
                    out_file.write(line)
        else:
            logger.info("couldn't attach jolokia to file, script not available " + sp);
    else:
        sp = sp + ".sh"
        if Path.exists(Path(sp)):
            jolokia_agent = \
                "    -javaagent:/opt/testgrid/agent/jolokia.jar=port=8778,host=localhost,protocol=http \\\n"
            with open(sp, "r") as in_file:
                buf = in_file.readlines()
            with open(sp, "w") as out_file:
                for line in buf:
                    if line == "    $JAVACMD \\\n":
                        line = line + jolokia_agent
                    out_file.write(line)
        else:
            logger.info("couldn't attach jolokia to file, script not available " + sp);


def copy_jar_file(source, destination):
    """Copy jar files from source to destination.
    """
    logger.info('sql driver is coping to the product lib folder')
    if sys.platform.startswith('win'):
        source = winapi_path(source)
        destination = winapi_path(destination)
    shutil.copy(source, destination)



def copy_file(source, target):
    """Copy the source file to the target.
    """
    if sys.platform.startswith('win'):
        source = winapi_path(source)
        target = winapi_path(target)
        shutil.copy(source, target)
    else:
        shutil.copy(source, target)


def modify_distribution_name(element):
    temp = element.text.split("/")
    temp[-1] = dist_name + ZIP_FILE_EXTENSION
    return '/'.join(temp)


def compress_distribution(distribution_path, root_dir):
    """Compress the distribution directory to a given location.
    """
    logger.info("Compressing files. From: " + str(root_dir) + " to: " + str(distribution_path))
    if type(distribution_path) == str:
        distribution_path = Path(distribution_path)
    if not Path.exists(distribution_path):
        Path(distribution_path).mkdir(parents=True, exist_ok=True)

    shutil.make_archive(distribution_path, "zip", root_dir)


def build_snapshot_dist(dist_path):
    """Build the distribution
    """
    zip_name = dist_name + ZIP_FILE_EXTENSION
    logger.info("Building snapshot with skip tests" )
    try:
        snapshot_build_dir_path = Path(workspace + "/" + product_id + "/")
        if sys.platform.startswith('win'):
            subprocess.call(['mvn', 'clean', 'install', '-B', '-e',
                             '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn',
                             '-Dmaven.test.skip=true'], shell=True, cwd=snapshot_build_dir_path)
        else:
            subprocess.call(['mvn', 'clean', 'install', '-B', '-e',
                             '-Dorg.slf4j.simpleLogger.log.org.apache.maven.cli.transfer.Slf4jMavenTransferListener=warn',
                             '-Dmaven.test.skip=true'], cwd=snapshot_build_dir_path)
    except Exception as e:
        logger.error("Error occurred while build the distribution",
                     exc_info=True)

    # copy the zip file to storage
    logger.info("Moving the Snapshot built file to :" + PRODUCT_STORAGE_DIR_NAME)
    storage_dir_path = Path(workspace + "/" + PRODUCT_STORAGE_DIR_NAME)
    snapshot_target_path = Path(workspace + "/" + product_id + "/" + dist_path)
    snapshot_zip_abs_path = Path(snapshot_target_path / zip_name)

    if os.path.exists(snapshot_zip_abs_path):
        if not os.path.exists(storage_dir_path):
            os.makedirs(storage_dir_path)
        # Remove the zip file and downloading the distribution from jenkins.
        os.remove(snapshot_zip_abs_path)
        get_latest_stable_dist()

    else:
        print("The file does not exist")


def add_distribution_to_m2(storage, m2_path):
    """Add the distribution zip into local .m2.
    """
    home = Path.home()
    m2_rel_path = ".m2/repository/org/wso2/" + m2_path
    #linux_m2_path = home / m2_rel_path / product_version / dist_name
    linux_m2_path = os.path.join(home,m2_rel_path,product_version,dist_name)
    windows_m2_path = Path("/Documents and Settings/Administrator/" + m2_rel_path + "/" + product_version + "/" + dist_name)
    if sys.platform.startswith('win'):
        windows_m2_path = winapi_path(windows_m2_path)
        storage = winapi_path(storage)
        compress_distribution(windows_m2_path, storage)
        shutil.rmtree(windows_m2_path, onerror=on_rm_error)
    else:
        compress_distribution(linux_m2_path, storage)
        shutil.rmtree(linux_m2_path, onerror=on_rm_error)


def save_test_output(reports_paths):
    report_folder = Path(workspace + "/" + TEST_OUTPUT_DIR_NAME + "/")
    report_file_paths = reports_paths
    if Path.exists(report_folder):
        shutil.rmtree(report_folder)
    if not Path.exists(report_folder):
        Path(report_folder).mkdir(parents=True, exist_ok=True)
    if report_file_paths:
        for file in report_file_paths:
            absolute_file_path = Path(workspace + "/" + product_id + "/" + file)
            if Path.exists(absolute_file_path):
                report_storage = Path(workspace + "/" + TEST_OUTPUT_DIR_NAME + "/")
                copy_file(absolute_file_path, report_storage)
                logger.info("Report successfully copied")
            else:
                logger.error("File doesn't contain in the given location: " + str(absolute_file_path))


def set_custom_testng(testng, testng_svr):
    testng_dest = testng
    testng_svr_mgt_dest = testng_svr
    if use_custom_testng_file.upper() == "TRUE":
        testng_source = Path(workspace + "/" + "testng.xml")
        testng_destination = Path(workspace + "/" + product_id + "/" + testng_dest)
        testng_server_mgt_source = Path(workspace + "/" + "testng-server-mgt.xml")
        testng_server_mgt_destination = Path(workspace + "/" + product_id + "/" + testng_svr_mgt_dest)
        # replace testng source
        replace_file(testng_source, testng_destination)
        # replace testng server mgt source
        replace_file(testng_server_mgt_source, testng_server_mgt_destination)
        logger.info("=== Customized testng files are copied to destination. ===")
