# CPAC/AWS/s3_sublist.py
#
# Author(s): Daniel Clark, 2015

'''
This module has functions to build a subject list from S3 and
local filepaths
'''

# Extract site-based scan parameters
def extract_scan_params(scan_params_csv):
    '''
    Function to extract the site-based scan parameters from a csv file
    and return a dictionary of their values

    Parameters
    ----------
    scan_params_csv : string
        filepath to the scan parameters csv file

    Returns
    -------
    site_dict : dictionary
        a dictionary where site names are the keys and the scan
        parameters for that site are the values stored as a dictionary
    '''

    # Import packages
    import csv

    # Init variables
    csv_open = open(scan_params_csv, 'r')
    site_dict = {}

    # Init csv dictionary reader
    reader = csv.DictReader(csv_open)

    # Iterate through the csv and pull in parameters
    for dict_row in reader:
        site = dict_row['Site']
        site_dict[site] = {key.lower() : val for key, val in dict_row.items()\
                           if key != 'Site'}
        # Assumes all other fields are formatted properly, but TR might not
        site_dict[site]['tr'] = site_dict[site].pop('tr (seconds)')

    # Return site dictionary
    return site_dict


# Check format of filepath templates
def check_template_format(file_template, site_kw, ppant_kw, sess_kw, ser_kw):
    '''
    '''

    # Import pacakges

    # Init variables

    # Check for ppant, series-level directories
    if not (ppant_kw in file_template and ser_kw in file_template):
        err_msg = 'Please provide \'%s\' and \'%s\' level directories in '\
                  'filepath template where participant and series-level '\
                  'directories are present in file template: %s' \
                  % (ppant_kw, ser_kw, file_template)
        raise Exception(err_msg)

    # Check to make sure all keywords are only used once in template
    if file_template.count(site_kw) > 1 or file_template.count(ppant_kw) or \
       file_template.count(sess_kw) > 1 or file_template.count(ser_kw) > 1:
        err_msg = 'There are multiple instances of key words in the provided '\
                  'file template: %s. Fix this and try again.' % file_template
        raise Exception(err_msg)


# Extract keyword from filepath
def extract_keyword_from_path(filepath, keyword, template):
    '''
    '''

    # Import packages

    # Init variables
    temp_split = template.split('/')
    fp_split = filepath.split('/')

    # Extract directory  name of the 
    kw_dirname = [dir for dir in temp_split if keyword in dir]

    # If the keyword is in the template, extract string from filepath
    if len(kw_dirname) == 1:
        # Get the directory fullname from template, as well as any surrounding
        kw_dirname = kw_dirname[0]
        kw_idx = temp_split.index(kw_dirname)
        # If the *'s straddle {keyword}, just include any found pattern as
        # extracted key string
        kw_prefix = kw_dirname.split(keyword)[0].replace('*', '')
        kw_suffix = kw_dirname.split(keyword)[-1].replace('*', '')

        # Extract directory with key string in it from filepath
        key_str = fp_split[kw_idx]
        # Strip out prefix/suffix
        if kw_prefix != '':
            key_str = key_str.split(kw_prefix)[-1]
        if kw_suffix != '':
            key_str = key_str.split(kw_suffix)[0]
    else:
        key_str = ''


# Filter out unwanted sites/subjects
def filter_sub_paths(sub_paths, include_sites, include_subs, exclude_subs,
                     site_kw, ppant_kw, path_template):
    '''
    Function to filter out unwanted sites and subjects from the
    collected filepaths

    Parameters
    ----------
    sub_paths : list
        a list of the subject data files
    include_sites : list or string
        indicates which sites to keep filepaths from
    include_subs : list or string
        indicates which subjects to keep filepaths from
    exclude_subs : list or string
        indicates which subjects to remove filepaths from
    path_template : string
        filepath template in the form of:
        '.../base_dir/{site}/{participant}/{session}/..
        {series}/file.nii.gz'

    Returns
    -------
    keep_subj_paths : list
        a list of the filepaths to use in the filtered subject list
    '''

    # Init variables
    path_split = path_template.split('/')

    # Check if {site} was specified
    if site_kw in path_template:
        # Find dir level with site_kw in it
        site_level = [dir for dir in path_split if site_kw in dir][0]
        site_idx = path_split.index(site_level)

        # Filter out sites that are not included
        if include_sites is not None:
            keep_site_paths = []
            if type(include_sites) is not list:
                include_sites = [include_sites]
            print 'Only including sites: %s' % include_sites
            for site in include_sites:
                site_matches = filter(lambda sp: sp.split('/')[site_idx] == \
                                      site_level.replace(site_kw, site),
                                      sub_paths)
                keep_site_paths.extend(site_matches)
                #sub_paths = [sp for sp in sub_paths if sp not in site_matches]
        else:
            keep_site_paths = sub_paths
    else:
        print '{site} not specified, not filtering out any potential sites...'

    # Find dir level with ppant_kw in it
    ppant_level = [dir for dir in path_split if ppant_kw in dir][0]
    ppant_idx = path_split.index(ppant_level)

    # Only keep subjects in inclusion list or remove those in exclusion list
    if include_subs is not None and exclude_subs is not None:
        err_msg = 'Please only populate subjects to include or exclude '\
                  '- not both!'
        raise Exception(err_msg)

    # Include only
    elif include_subs is not None:
        keep_subj_paths = []
        if type(include_subs) is not list:
            include_subs = [include_subs]
        print 'Only including subjects: %s' % include_subs
        for inc_sub in include_subs:
            sub_matches = filter(lambda sp: sp.split('/')[ppant_idx] == \
                                 ppant_level.replace(ppant_kw, inc_sub),
                                 keep_site_paths)
            keep_subj_paths.extend(sub_matches)

    # Or exclude only
    elif exclude_subs is not None:
        keep_subj_paths = []
        if type(exclude_subs) is not list:
            exclude_subs = [exclude_subs]
        print 'Including all subjects but: %s' % exclude_subs
        for exc_sub in exclude_subs:
            sub_matches = filter(lambda sp: sp.split('/')[ppant_idx] != \
                                 ppant_level.replace(ppant_kw, exc_sub),
                                 keep_site_paths)
            keep_subj_paths.extend(sub_matches)

    else:
        keep_subj_paths = keep_site_paths

    # Return kept paths
    return keep_subj_paths


# # Get site, ppant, session-level directory indicies
# def return_dir_indices(path_template):
#     '''
#     Function to return the site, particpant, and session-level
#     directory indicies based on splitting the path template by
#     directory seperation '/'
# 
#     Parameters
#     ----------
#     path_template : string
#         filepath template in the form of:
#         '.../base_dir/{site}/{participant}/{session}/..
#         {series}/file.nii.gz'
# 
#     Returns
#     -------
#     site_idx : integer
#         the directory level of site folders
#     ppant_idx : integer
#         the directory level of participant folders
#     sess_idx : integer
#         the directory level of the session folders
#     series_idx : integer
#         the directory level of the series folder
#     '''
# 
#     # Get folder level indices of site and subject - anat
#     fp_split = path_template.split('/')
# 
#     # Site level isn't required, but recommended
#     try:
#         site_idx = fp_split.index('{site}')
#     except ValueError as exc:
#         site_idx = -1
# 
#     # Get required participant directory index
#     ppant_idx = fp_split.index('{participant}')
# 
#     # Session level isn't required, but recommended
#     try:
#         sess_idx = fp_split.index('{session}')
#     except ValueError as exc:
#         sess_idx = -1
# 
#     # Get required series directory index
#     series_idx = fp_split.index('{series}')
# 
#     # Return indices
#     return site_idx, ppant_idx, sess_idx, series_idx


# Return matching filepaths
def return_local_filepaths(file_pattern):
    '''
    Function to return the filepaths from local directories given a
    file pattern template

    Parameters
    ----------
    file_pattern : string
        regexp and glob compatible file pattern for gathering local
        files

    Returns
    -------
    local_filepaths : list
        a list of strings of the local filepaths
    '''

    # Import packages
    import glob
    import os

    # Gather local files
    local_filepaths = glob.glob(file_pattern)

    # Get absolute paths
    local_filepaths = [os.path.abspath(fp) for fp in local_filepaths]

    # Print how many found
    num_local_files = len(local_filepaths)
    print 'Found %d files!' % num_local_files

    # Return the filepaths as a list
    return local_filepaths


# Return matching filepaths
def return_s3_filepaths(file_pattern, creds_path=None):
    '''
    Function to return the filepaths from an S3 bucket given a file
    pattern template and, optionally, credentials

    Parameters
    ----------
    file_pattern : string
        regexp and glob compatible file pattern for gathering local
        files
    creds_path : string (optional); default=None
        filepath to a credentials file containing the AWS credentials
        to access the S3 bucket objects

    Returns
    -------
    s3_filepaths : list
        a list of strings of the filepaths from the S3 bucket
    '''

    # Import packages
    import fnmatch
    import os
    import re

    from CPAC.AWS import fetch_creds

    # Init variables
    bucket_name = file_pattern.split('/')[2]
    s3_prefix = '/'.join(file_pattern.split('/')[:3])

    # Find non regular expression patterns to get prefix
    s3_rel_path = file_pattern.replace(s3_prefix, '').lstrip('/')
    fp_split = s3_rel_path.split('/')
    for idx, dir in enumerate(fp_split):
        # Search for characters that we're permitting to be in folder names
        ok_chars = [char in dir for char in ['_', '-', '^']]
        if any(ok_chars):
            continue

        # Put escape '\' character in front of any non alphanumeric character
        reg_dir = re.escape(dir)

        # If we find a non alpha-numeric character in string, break
        if reg_dir != dir:
            break

    # Use all dirs up to first directory with non alpha-numeric character
    # as prefix
    prefix = '/'.join(fp_split[:idx])

    # Attempt to get bucket
    try:
        bucket = fetch_creds.return_bucket(creds_path, bucket_name)
    except Exception as exc:
        err_msg = 'There was an error in retrieving S3 bucket: %s.\nError: %s'\
                  %(bucket_name, exc)
        raise Exception(err_msg)

    # Get filepaths from S3 with prefix
    print 'Gathering files from S3 to parse...'
    s3_filepaths = []
    for s3_obj in bucket.objects.filter(Prefix=prefix):
        s3_filepaths.append(str(s3_obj.key))

    # Prepend 's3://bucket_name/' on found paths
    s3_filepaths = [os.path.join(s3_prefix, s3_fp) for s3_fp in s3_filepaths]

    # File pattern filter
    s3_filepaths = fnmatch.filter(s3_filepaths, file_pattern)

    # Print how many found
    num_s3_files = len(s3_filepaths)
    print 'Found %d files!' % num_s3_files

    # Return the filepaths as a list
    return s3_filepaths


# Build the C-PAC subject list
def build_sublist(data_config_yml):
    '''
    Function to build a C-PAC-compatible subject list, given
    anatomical and functional file paths

    Parameters
    ----------
    data_config_yml : string
        filepath to the data config yaml file

    Returns
    -------
    sublist : list
        C-PAC subject list of subject dictionaries
    '''

    # Import packages
    import os
    import yaml

    # Init variables
    site_kw = '{site}'
    ppant_kw = '{participant}'
    sess_kw = '{session}'
    ser_kw = '{series}'

    tmp_dict = {}
    s3_str = 's3://'

    # Load in data config from yaml to dictionary
    data_config_dict = yaml.load(open(data_config_yml, 'r'))

    # Get inclusion, exclusion, scan csv parameters, and output location
    anat_template = data_config_dict['anatomicalTemplate']
    func_template = data_config_dict['functionalTemplate']
    include_subs = data_config_dict['subjectList']
    exclude_subs = data_config_dict['exclusionSubjectList']
    include_sites = data_config_dict['siteList']
    scan_params_csv = data_config_dict['scanParametersCSV']
    sublist_outdir = data_config_dict['outputSubjectListLocation']
    sublist_name = data_config_dict['subjectListName']
    # Older data configs won't have this field
    try:
        creds_path = data_config_dict['awsCredentialsFile']
    except KeyError:
        creds_path = None

    # Change any 'None' to None of optional arguments
    if include_subs == 'None':
        include_subs = None
    if exclude_subs == 'None':
        exclude_subs = None
    if include_sites == 'None':
        include_sites = None
    if scan_params_csv == 'None':
        scan_params_csv = None
    if creds_path == 'None':
        creds_path = None

    # Check templates for proper formatting
    check_template_format(anat_template)
    check_template_format(func_template)

    # Replace keywords with glob regex wildcards
    anat_pattern = anat_template.replace(site_kw, '*').replace(ppant_kw, '*').\
                   replace(sess_kw, '*').replace(ser_kw, '*')
    func_pattern = func_template.replace(site_kw, '*').replace(ppant_kw, '*').\
                   replace(sess_kw, '*').replace(ser_kw, '*')

    # See if the templates are s3 files
    if s3_str in anat_template.lower() and s3_str in func_template.lower():
        # Get anatomical filepaths from s3
        print 'Fetching anatomical files...'
        anat_paths = return_s3_filepaths(anat_pattern, creds_path)
        # Get functional filepaths from s3
        print 'Fetching functional files...'
        func_paths = return_s3_filepaths(func_pattern, creds_path)

    # If one is in S3 and the other is not, raise error - not supported
    elif (s3_str in anat_template.lower() and s3_str not in func_template.lower()) or \
         (s3_str not in anat_template.lower() and s3_str in func_template.lower()):
        err_msg = 'Both anatomical and functional files should either be '\
                  'on S3 or local. Separating the files is currently not '\
                  'supported.'
        raise Exception(err_msg)

    # Otherwise, it's local files
    else:
        # Get anatomical filepaths
        print 'Gathering anatomical files...'
        anat_paths = return_local_filepaths(anat_pattern)
        # Get functional filepaths
        print 'Gathering functional files...'
        func_paths = return_local_filepaths(func_pattern)

    # Get directory indicies
#     anat_site_idx, anat_ppant_idx, anat_sess_idx, anat_series_idx = \
#         return_dir_indices(anat_template)
#     func_site_idx, func_ppant_idx, func_sess_idx, func_series_idx = \
#         return_dir_indices(func_template)

    # Filter out unwanted anat and func filepaths
    anat_paths = filter_sub_paths(anat_paths, include_sites,
                                  include_subs, exclude_subs,
                                  site_kw, ppant_kw, anat_template)
    print 'Filtered down to %d anatomical files' % len(anat_paths)

    func_paths = filter_sub_paths(func_paths, include_sites,
                                  include_subs, exclude_subs,
                                  site_kw, ppant_kw, func_template)
    print 'Filtered down to %d functional files' % len(func_paths)

    # If all data is filtered out, raise exception
    if len(anat_paths) == 0 or len(func_paths) == 0:
        err_msg = 'Unable to find any files after filtering sites and '\
                  'subjects! Check site and subject inclusion/exclusion fields!'
        raise Exception(err_msg)

    # Read in scan parameters and return site-based dictionary
    if scan_params_csv is not None:
        site_scan_params = extract_scan_params(scan_params_csv)
    else:
        site_scan_params = {}

    # Iterate through file paths and build subject list
    for anat in anat_paths:
        site = extract_keyword_from_path(anat, site_kw, anat_template)

        # Test for optional site folder
        if anat_site_idx != -1:
            site = anat_sp[anat_site_idx]
        else:
            site = ''

        # Participant id
        subj = anat_sp[anat_ppant_idx]

        # Test for optional session folder
        if anat_sess_idx != -1:
            sess = anat_sp[anat_sess_idx]
        else:
            sess = ''

#         # Series id
#         series = anat_sp[anat_series_idx]

        # Init dictionary
        subj_d = {'anat' : anat, 'creds_path' : creds_path, 'rest' : {},
                  'subject_id' : subj, 'unique_id' : '_'.join([site, sess])}

        # Check for scan parameters
        if scan_params_csv is not None:
            try:
                subj_d['scan_parameters'] = site_scan_params[site]
            except KeyError as exc:
                print 'Site %s missing from scan parameters csv, skipping...'\
                      % site

        # Test to make sure subject key isn't present already
        # Should be a unique entry for every anatomical image
        tmp_key = '_'.join([site, subj, sess])
        if tmp_dict.has_key(tmp_key):
            err_msg = 'Key for anatomical file already exists: %s\n'\
                      'Either duplicate scan or data needs re-organization to '\
                      'differentiate between subjects from different sites/sessions'
            raise Exception(err_msg)

        tmp_dict[tmp_key] = subj_d

    # Now go through and populate functional scans dictionaries
    for func in func_paths:
        # Extract info from filepath
        func_sp = func.split('/')
        # Test for optional site folder
        if func_site_idx != -1:
            site = func_sp[func_site_idx]
        else:
            site = ''

        # Participant id
        subj = func_sp[func_ppant_idx]

        # Test for optional session folder
        if func_sess_idx != -1:
            sess = func_sp[func_sess_idx]
        else:
            sess = ''

        # Series id
        series = func_sp[func_series_idx]

        # Build tmp key and get subject dictionary from tmp dictionary
        tmp_key = '_'.join([site, subj, sess])
        # Try and find the associated anat scan
        try:
            subj_d = tmp_dict[tmp_key]
        except KeyError as exc:
            print 'Unable to find anatomical image for %s. Skipping...' \
                  % tmp_key
            continue
        # Set the rest dictionary with the scan
        subj_d['rest'][series] = func
        # And replace it back in the dictionary
        tmp_dict[tmp_key] = subj_d

    # Build a subject list from dictionary values
    sublist = [v for v in tmp_dict.values()]

    # Write subject list out to out location
    sublist_out_yml = os.path.join(sublist_outdir,
                                   'CPAC_subject_list_%s.yml' % sublist_name)
    with open(sublist_out_yml, 'w') as out_sublist:
        # Make sure YAML doesn't dump aliases (so it's more human read-able)
        noalias_dumper = yaml.dumper.SafeDumper
        noalias_dumper.ignore_aliases = lambda self, data: True
        out_sublist.write(yaml.dump(sublist, default_flow_style=False,
                                    Dumper=noalias_dumper))

    # Return the subject list
    return sublist
