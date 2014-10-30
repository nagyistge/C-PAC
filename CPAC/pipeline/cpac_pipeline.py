import os
import time
from time import strftime
import nipype.pipeline.engine as pe
import nipype.interfaces.fsl as fsl
import nipype.interfaces.io as nio
from nipype.interfaces.afni import preprocess
from   nipype.pipeline.utils import format_dot
import nipype.interfaces.ants as ants
import nipype.interfaces.c3 as c3
from nipype import config
from nipype import logging
from CPAC import network_centrality
from CPAC.network_centrality.utils import merge_lists
logger = logging.getLogger('workflow')
import pkg_resources as p
#import CPAC
from CPAC.anat_preproc.anat_preproc import create_anat_preproc
from CPAC.func_preproc.func_preproc import create_func_preproc, create_wf_edit_func
from CPAC.seg_preproc.seg_preproc import create_seg_preproc

from CPAC.registration import create_nonlinear_register, \
                              create_register_func_to_anat, \
                              create_bbregister_func_to_anat, \
                              create_wf_calculate_ants_warp, \
                              create_wf_apply_ants_warp, \
                              create_wf_c3d_fsl_to_itk, \
                              create_wf_collect_transforms
from CPAC.nuisance import create_nuisance, bandpass_voxels

from CPAC.median_angle import create_median_angle_correction
from CPAC.generate_motion_statistics import motion_power_statistics
from CPAC.generate_motion_statistics import fristons_twenty_four
from CPAC.scrubbing import create_scrubbing_preproc
from CPAC.timeseries import create_surface_registration, get_roi_timeseries, \
                            get_voxel_timeseries, get_vertices_timeseries, \
                            get_spatial_map_timeseries
from CPAC.network_centrality import create_resting_state_graphs, \
                                    get_cent_zscore
from CPAC.utils.datasource import *
from CPAC.utils import Configuration, create_all_qc
### no create_log_template here, move in CPAC/utils/utils.py
from CPAC.qc.qc import create_montage, create_montage_gm_wm_csf
from CPAC.qc.utils import register_pallete, make_edge, drop_percent_, \
                          gen_histogram, gen_plot_png, gen_motion_plt, \
                          gen_std_dev, gen_func_anat_xfm, gen_snr, \
                          generateQCPages, cal_snr_val
from CPAC.utils.utils import extract_one_d, set_gauss, \
                             process_outputs, get_scan_params, \
                             get_tr, extract_txt, create_log, \
                             create_log_template, extract_output_mean, \
                             create_output_mean_csv, get_zscore, \
                             get_fisher_zscore, dbg_file_lineno
from CPAC.vmhc.vmhc import create_vmhc
from CPAC.reho.reho import create_reho
from CPAC.alff.alff import create_alff
from CPAC.sca.sca import create_sca, create_temporal_reg
from CPAC.pipeline.utils import    strategy, create_log_node, logStandardError,\
                        logConnectionError, logStandardWarning,getNodeList,\
                        inputFilepathsCheck, workflowPreliminarySetup,\
                        runAnatomicalDataGathering, runAnatomicalPreprocessing,\
                        runRegistrationPreprocessing, runSegmentationPreprocessing,\
                        runFunctionalDataGathering, collect_transforms_func_mni,\
                        fsl_to_itk_conversion, ants_apply_warps_func_mni,\
                        fisher_z_score_standardize, z_score_standardize,\
                        connectCentralityWorkflow, output_smooth,\
                        output_smooth_FuncToMNI,output_to_standard, pick_wm, \
                        runFristonModel, runRegisterFuncToAnat,\
                        runGenerateMotionStatistics,runALFF,runReHo,\
                        runMedianAngleCorrection, runFrequencyFiltering,\
                        runSCAforROIinput, runNuisance, runSpatialRegression,\
                        runScrubbing, runVMHC, func2T1BBREG
import zlib
import linecache
import csv
import pickle
import CPAC

 

def prep_workflow(sub_dict, c, strategies, run, pipeline_timing_info=None, p_name=None):


    """""""""""""""""""""""""""""""""""""""""""""""""""
     SETUP
    """""""""""""""""""""""""""""""""""""""""""""""""""

    '''
    preliminaries
    '''

    # Start timing here
    pipeline_start_time = time.time()
    # at end of workflow, take timestamp again, take time elapsed and check
    # tempfile add time to time data structure inside tempfile, and increment
    # number of subjects

    cores_msg = 'VERSION: CPAC %s' % CPAC.__version__

    # perhaps in future allow user to set threads maximum
    # this is for centrality mostly    
    # import mkl
    numThreads = '1'

    os.environ['OMP_NUM_THREADS'] = numThreads
    os.environ['MKL_NUM_THREADS'] = numThreads
    os.environ['ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS'] = str(c.num_ants_threads)

    # calculate maximum potential use of cores according to current pipeline
    # configuration
    max_core_usage = int(c.numCoresPerSubject) * int(c.numSubjectsAtOnce) * \
                         int(numThreads) * int(c.num_ants_threads)

    cores_msg = cores_msg + '\n\nSetting OMP_NUM_THREADS to %s\n' % numThreads
    cores_msg = cores_msg + 'Setting MKL_NUM_THREADS to %s\n' % numThreads
    cores_msg = cores_msg + 'Setting ANTS/ITK thread usage to %d\n\n' \
                % c.num_ants_threads

    cores_msg = cores_msg + 'Potential maximum number of cores '\
                    'for this run: %d\n\n' % max_core_usage

    cores_msg = cores_msg + 'If that\'s more cores than you have, fix this by \n' \
                'adjusting the following settings in pipeline config editor:\n '\
                '\'Number of Cores Per Subject\',\n \'Number of Subjects ' \
                'to Run Simultaneously\',\n and \'Number of Cores for ' \
                'Anatomical Registration (ANTS only)\'\n'
    logger.info(cores_msg)


    qc_montage_id_a = {}
    qc_montage_id_s = {}
    qc_plot_id = {}
    qc_hist_id = {}
    if sub_dict['unique_id']:
        subject_id = sub_dict['subject_id'] + "_" + sub_dict['unique_id']
    else:
        subject_id = sub_dict['subject_id']
        
    log_dir = os.path.join(c.outputDirectory, 'logs', subject_id)

    if not os.path.exists(log_dir):
        os.makedirs(os.path.join(log_dir))


    inputFilepathsCheck(c)
    workflow=workflowPreliminarySetup(subject_id,c,config,logging,log_dir,logger)
    workflow_bit_id = {}
    workflow_counter = 0
    strat_list = []
    

    """""""""""""""""""""""""""""""""""""""""""""""""""
     PREPROCESSING
    """""""""""""""""""""""""""""""""""""""""""""""""""

    '''
    Initialize Anatomical Input Data Flow
    '''
    strat_list = runAnatomicalDataGathering(c,subject_id,sub_dict,workflow,\
                                workflow_bit_id,workflow_counter,\
                                strat_list,logger,log_dir)

    '''
    Inserting Anatomical Preprocessing workflow
    '''
    strat_list = runAnatomicalPreprocessing(c,subject_id,sub_dict,workflow,\
                                workflow_bit_id,workflow_counter,strat_list,logger,log_dir)

    '''
    T1 -> Template, Non-linear registration (FNIRT or ANTS)
    '''
    workflow_counter += 1
    strat_list = runRegistrationPreprocessing(c,subject_id,sub_dict,workflow,\
                                workflow_bit_id,workflow_counter,strat_list,logger,log_dir)

    '''
    Inserting Segmentation Preprocessing
    Workflow
    '''
    workflow_counter += 1
    strat_list=runSegmentationPreprocessing(c,subject_id,sub_dict,workflow,\
                                workflow_bit_id,workflow_counter,\
                                strat_list,logger,log_dir)

    '''
    Inserting Functional Data workflow
    '''

##    strat_list,funcFlow = runFunctionalDataGathering(c,subject_id,sub_dict,workflow,\
##                                workflow_bit_id,workflow_counter,\
##                                strat_list,logger,log_dir)
##
##
##    """
##    Inserting Functional Image Preprocessing
##    Workflow
##    """   
##    workflow_counter += 1
##    strat_list = runFunctionalPreprocessing(c,subject_id,sub_dict,workflow,\
##                                workflow_bit_id,workflow_counter,\
##                                strat_list,logger,log_dir)


    num_strat = 0
    if 1 in c.runFunctionalDataGathering:
        for strat in strat_list:
            # create a new node, Remember to change its name!
            # Flow = create_func_datasource(sub_dict['rest'])
            # Flow.inputs.inputnode.subject = subject_id
            try: 
                funcFlow = create_func_datasource(sub_dict['rest'], 'func_gather_%d' % num_strat)
                funcFlow.inputs.inputnode.subject = subject_id
            except Exception as xxx:
                logger.info( "Error create_func_datasource failed."+\
                      " (%s:%d)" % dbg_file_lineno() )
                raise

            """
            Add in nodes to get parameters from configuration file
            """
            try:
                # a node which checks if scan _parameters are present for each scan
                scan_params = pe.Node(util.Function(input_names=['subject','scan','subject_map',
                                                                 'start_indx','stop_indx','tr','tpattern'],
                                                    output_names=['tr','tpattern','ref_slice',
                                                                 'start_indx','stop_indx'],
                                                    function=get_scan_params),
                                       name='scan_params_%d' % num_strat)
            except Exception as xxx:
                logger.info( "Error creating scan_params node."+\
                      " (%s:%d)" % dbg_file_lineno() )
                raise

   
            # wire in the scan parameter workflow
            try:
                workflow.connect(funcFlow, 'outputspec.subject',
                                 scan_params, 'subject')
            except Exception as xxx:
                logger.info( "Error connecting scan_params 'subject' input."+\
                      " (%s:%d)" % dbg_file_lineno() )
                raise

            try:
                workflow.connect(funcFlow, 'outputspec.scan',
                                 scan_params, 'scan')
            except Exception as xxx:
                logger.info( "Error connecting scan_params 'scan' input."+\
                      " (%s:%d)" % dbg_file_lineno() )
                raise

            # connect in constants
            scan_params.inputs.subject_map = sub_dict
            scan_params.inputs.start_indx = c.startIdx
            scan_params.inputs.stop_indx = c.stopIdx
            scan_params.inputs.tr = c.TR
            scan_params.inputs.tpattern = c.slice_timing_pattern[0]
    
            # node to convert TR between seconds and milliseconds
            try:
                convert_tr = pe.Node(util.Function(input_names=['tr'],
                                                   output_names=['tr'],
                                                   function=get_tr),
                                    name='convert_tr_%d' % num_strat)
            except Exception as xxx:
                logger.info( "Error creating convert_tr node."+\
                      " (%s:%d)" % dbg_file_lineno() )
                raise
    
            try:    
                workflow.connect(scan_params, 'tr',
                                  convert_tr, 'tr')
            except Exception as xxx:
                logger.info( "Error connecting convert_tr 'tr' input."+\
                      " (%s:%d)" % dbg_file_lineno() )
                raise
    

            strat.set_leaf_properties(funcFlow, 'outputspec.rest')

            num_strat += 1

        """
        Truncate scan length based on configuration information
        """

        num_strat = 0

        for strat in strat_list:
            try:
                trunc_wf=create_wf_edit_func( wf_name = "edit_func_%d"%(num_strat))
            except Exception as xxx:
                logger.info( "Error create_wf_edit_func failed."+\
                      " (%s:%d)" %(dbg_file_lineno()))
                raise

            # find the output data on the leaf node
            try:
                node, out_file = strat.get_leaf_properties()
            except Exception as xxx:
                logger.info( "Error  get_leaf_properties failed."+\
                      " (%s:%d)" % dbg_file_lineno() )
                raise

            # connect the functional data from the leaf node into the wf
            try:
                workflow.connect(node, out_file, trunc_wf, 'inputspec.func')
            except Exception as xxx:
                logger.info( "Error connecting input 'func' to trunc_wf."+\
                      " (%s:%d)" % dbg_file_lineno() )
                print xxx
                raise

            # connect the other input parameters
            try: 
                workflow.connect(scan_params, 'start_indx',
                                 trunc_wf, 'inputspec.start_idx')
            except Exception as xxx:
                logger.info( "Error connecting input 'start_indx' to trunc_wf."+\
                      " (%s:%d)" % dbg_file_lineno() )
                raise

            try:
                workflow.connect(scan_params, 'stop_indx',
                                 trunc_wf, 'inputspec.stop_idx')
            except Exception as xxx:
                logger.info( "Error connecting input 'stop_idx' to trunc_wf."+\
                      " (%s:%d)" % dbg_file_lineno() )
                raise

   
            # replace the leaf node with the output from the recently added workflow 
            strat.set_leaf_properties(trunc_wf, 'outputspec.edited_func')
            num_strat = num_strat+1


        """
        Inserting slice timing correction
        Workflow
        """
        new_strat_list = []
        num_strat = 0
    
        if 1 in c.slice_timing_correction:
    
            for strat in strat_list:

                # create TShift AFNI node
                try:
                    func_slice_timing_correction = pe.Node(interface=preprocess.TShift(),
                        name = 'func_slice_timing_correction_%d'%(num_strat))
                    func_slice_timing_correction.inputs.outputtype = 'NIFTI_GZ'
                except Exception as xxx:
                    logger.info( "Error connecting input 'stop_idx' to trunc_wf."+\
                          " (%s:%d)" % dbg_file_lineno() )
                    raise

                # find the output data on the leaf node
                try:
                    node, out_file = strat.get_leaf_properties()
                except Exception as xxx:
                    logger.info( "Error  get_leaf_properties failed."+\
                          " (%s:%d)" % dbg_file_lineno() )
                    raise

   
                # connect the output of the leaf node as the in_file
                try:
                    workflow.connect(node, out_file,
                        func_slice_timing_correction,'in_file')
                except Exception as xxx:
                    logger.info( "Error connecting input 'infile' to func_slice_timing_correction afni node."+\
                          " (%s:%d)" % dbg_file_lineno() )
                    raise

                logger.info("connected input to slc")
                # we might prefer to use the TR stored in the NIFTI header
                # if not, use the value in the scan_params node
                logger.info( "TR %s" %c.TR)
                if c.TR:
                    try:
                        workflow.connect(scan_params, 'tr',
                            func_slice_timing_correction, 'tr')
                    except Exception as xxx:
                        logger.info( "Error connecting input 'tr' to func_slice_timing_correction afni node."+\
                             " (%s:%d)" % dbg_file_lineno() )
                        print xxx
                        raise
                    logger.info("connected TR")

                # we might prefer to use the slice timing information stored in the NIFTI header
                # if not, use the value in the scan_params node
                logger.info( "slice timing pattern %s"%c.slice_timing_pattern[0])
                try:
                    if not "Use NIFTI Header" in c.slice_timing_pattern[0]:
                        try:
                            logger.info( "connecting slice timing pattern %s"%c.slice_timing_pattern[0])
                            workflow.connect(scan_params, 'tpattern',
                                func_slice_timing_correction, 'tpattern')
                            logger.info( "connected slice timing pattern %s"%c.slice_timing_pattern[0])
                        except Exception as xxx:
                            logger.info( "Error connecting input 'acquisition' to func_slice_timing_correction afni node."+\
                                 " (%s:%d)" % dbg_file_lineno() )
                            print xxx
                            raise
                        logger.info( "connected slice timing pattern %s"%c.slice_timing_pattern[0])
                except Exception as xxx:
                    logger.info( "Error connecting input 'acquisition' to func_slice_timing_correction afni node."+\
                                 " (%s:%d)" % dbg_file_lineno() )
                    print xxx
                    raise

                if (0 in c.runFunctionalPreprocessing):
                    # we are forking so create a new node
                    tmp = strategy()
                    tmp.resource_pool = dict(strat.resource_pool)
                    tmp.leaf_node = (strat.leaf_node)
                    tmp.leaf_out_file = str(strat.leaf_out_file)
                    tmp.name = list(strat.name)
                    strat = tmp
                    new_strat_list.append(strat)
   
                # add the name of the node to the strat name
                strat.append_name(func_slice_timing_correction.name)
   
                # set the leaf node 
                strat.set_leaf_properties(func_slice_timing_correction, 'out_file')

                # add the outputs to the resource pool
                strat.update_resource_pool({'slice_time_corrected':(func_slice_timing_correction, 'out_file')},logger)
                num_strat += 1
   
            # add new strats (if forked) 
            strat_list += new_strat_list
    
            logger.info( " finsihed connected slice timing pattern")

        """
        Inserting Functional Image Preprocessing Workflow
        """
        new_strat_list = []
        num_strat = 0
    
        workflow_counter += 1
    
        if 1 in c.runFunctionalPreprocessing:
    
            workflow_bit_id['func_preproc'] = workflow_counter
    
            for strat in strat_list:
    
                if '3dAutoMask' in c.functionalMasking:
    
                    try:
                        func_preproc = create_func_preproc(use_bet=False, wf_name='func_preproc_automask_%d' % num_strat)
                    except Exception as xxx:
                        logger.info( "Error allocating func_preproc."+\
                             " (%s:%d)" % dbg_file_lineno() )
                        raise

                    node = None
                    out_file = None
                    try:
                        node, out_file = strat.get_leaf_properties()
                        logger.info("%s::%s==>%s"%(node, out_file,func_preproc)) 
                        try:
                            workflow.connect(node, out_file, func_preproc, 'inputspec.func')
                        except Exception as xxx:
                            logger.info( "Error connecting leafnode to func, func_preproc."+\
                                 " (%s:%d)" % (dbg_file_lineno()) )
                            print xxx
                            raise
                        logger.info("infile rest connected") 
                    except Exception as xxx:
                        logConnectionError('Functional Preprocessing', num_strat, strat.get_resource_pool(), '0005_automask',logger)
                        num_strat += 1
                        raise
    
                    if (0 in c.runFunctionalPreprocessing) or ('BET' in c.functionalMasking):
                        # we are forking so create a new node
                        tmp = strategy()
                        tmp.resource_pool = dict(strat.resource_pool)
                        tmp.leaf_node = (strat.leaf_node)
                        tmp.leaf_out_file = str(strat.leaf_out_file)
                        tmp.name = list(strat.name)
                        strat = tmp
                        new_strat_list.append(strat)
    
                    strat.append_name(func_preproc.name)    
                    strat.set_leaf_properties(func_preproc, 'outputspec.preprocessed')
    
                    # add stuff to resource pool if we need it
                    strat.update_resource_pool({'mean_functional':(func_preproc, 'outputspec.example_func')},logger)
                    strat.update_resource_pool({'functional_preprocessed_mask':(func_preproc, 'outputspec.preprocessed_mask')},logger)
                    strat.update_resource_pool({'movement_parameters':(func_preproc, 'outputspec.movement_parameters')},logger)
                    strat.update_resource_pool({'max_displacement':(func_preproc, 'outputspec.max_displacement')},logger)
                    strat.update_resource_pool({'preprocessed':(func_preproc, 'outputspec.preprocessed')},logger)
                    strat.update_resource_pool({'functional_brain_mask':(func_preproc, 'outputspec.mask')},logger)
                    strat.update_resource_pool({'motion_correct':(func_preproc, 'outputspec.motion_correct')},logger)
                    strat.update_resource_pool({'coordinate_transformation':(func_preproc, 'outputspec.oned_matrix_save')},logger)
    
    
                    create_log_node(workflow,func_preproc, 'outputspec.preprocessed', num_strat,log_dir)
                    num_strat += 1
    
            strat_list += new_strat_list
    
            new_strat_list = []
                
    
            for strat in strat_list:
                
                nodes = getNodeList(strat)
                
                if ('BET' in c.functionalMasking) and ('func_preproc_automask' not in nodes):
    
                    func_preproc = create_func_preproc( use_bet=True, \
                                                        wf_name='func_preproc_bet_%d' % num_strat)
                    node = None
                    out_file = None
                    try:
                        node, out_file = strat.get_leaf_properties()
                        workflow.connect(node, out_file, func_preproc, 'inputspec.func')
    
                    except Exception as xxx:
                        logConnectionError('Functional Preprocessing', num_strat, strat.get_resource_pool(), '0005_bet',logger)
                        num_strat += 1
                        raise
    
                    if 0 in c.runFunctionalPreprocessing:
                        # we are forking so create a new node
                        tmp = strategy()
                        tmp.resource_pool = dict(strat.resource_pool)
                        tmp.leaf_node = (strat.leaf_node)
                        tmp.leaf_out_file = str(strat.leaf_out_file)
                        tmp.name = list(strat.name)
                        strat = tmp
                        new_strat_list.append(strat)
    
                    strat.append_name(func_preproc.name)
    
                    strat.set_leaf_properties(func_preproc, 'outputspec.preprocessed')
    
                    # add stuff to resource pool if we need it
                    strat.update_resource_pool({'mean_functional':(func_preproc, 'outputspec.example_func')},logger)
                    strat.update_resource_pool({'functional_preprocessed_mask':(func_preproc, 'outputspec.preprocessed_mask')},logger)
                    strat.update_resource_pool({'movement_parameters':(func_preproc, 'outputspec.movement_parameters')},logger)
                    strat.update_resource_pool({'max_displacement':(func_preproc, 'outputspec.max_displacement')},logger)
                    strat.update_resource_pool({'preprocessed':(func_preproc, 'outputspec.preprocessed')},logger)
                    strat.update_resource_pool({'functional_brain_mask':(func_preproc, 'outputspec.mask')},logger)
                    strat.update_resource_pool({'motion_correct':(func_preproc, 'outputspec.motion_correct')},logger)
                    strat.update_resource_pool({'coordinate_transformation':(func_preproc, 'outputspec.oned_matrix_save')},logger)
                    create_log_node(workflow,func_preproc, 'outputspec.preprocessed', num_strat,log_dir)
                    num_strat += 1
    
        strat_list += new_strat_list
    
        '''
        Inserting Friston's 24 parameter Workflow
        In case this workflow runs , it overwrites the movement_parameters file
        So the file contains 24 parameters for motion and that gets wired to all the workflows
        that depend on. The effect should be seen when regressing out nuisance signals and motion
        is used as one of the regressors
        '''        
        workflow_counter += 1
        num_strat = runFristonModel(c,subject_id,sub_dict,workflow,workflow_bit_id,\
                    workflow_counter,strat_list,logger,log_dir)

    '''
    Func -> T1 Registration (Initial Linear reg)
    Depending on configuration, either passes output matrix to 
    Func -> Template ApplyWarp, or feeds into linear reg of BBReg operation 
    (if BBReg is enabled)
    '''
    workflow_counter += 1
    strat_list = runRegisterFuncToAnat(c,subject_id,sub_dict,workflow,workflow_bit_id,\
                            workflow_counter,strat_list,logger,log_dir)
 
    '''
    Func -> T1 Registration (BBREG)
    Outputs 'functional_to_anat_linear_xfm', a matrix file of the 
    functional-to-anatomical registration warp to be applied LATER in 
    func_mni_warp, which accepts it as input 'premat'
    '''    
    workflow_counter += 1
    strat_list = func2T1BBREG(c,subject_id,sub_dict,workflow,workflow_bit_id,\
                    workflow_counter,strat_list,logger,log_dir)

    '''
    Inserting Generate Motion Statistics Workflow
    '''
    workflow_counter += 1
    strat_list = runGenerateMotionStatistics(c,subject_id,sub_dict,workflow,\
                    workflow_bit_id,workflow_counter,strat_list,logger,\
                    log_dir,funcFlow)

    '''
    Inserting Nuisance Workflow
    '''
    workflow_counter += 1
    strat_list = runNuisance(c,subject_id,sub_dict,workflow,workflow_bit_id,\
                workflow_counter,strat_list,logger,log_dir)

    '''
    Inserting Median Angle Correction Workflow
    '''
    workflow_counter += 1
    strat_list = runMedianAngleCorrection(c,subject_id,sub_dict,workflow,\
                    workflow_bit_id,workflow_counter,strat_list,logger,log_dir)

    '''
    Inserting ALFF/fALFF Workflow
    '''
    strat_list = runALFF(c,subject_id,sub_dict,workflow,workflow_bit_id,\
                            workflow_counter,strat_list,logger,log_dir)

    '''
    Inserting Frequency Filtering Node
    '''
    workflow_counter += 1
    strat_list = runFrequencyFiltering(c,subject_id,sub_dict,workflow,\
                        workflow_bit_id,workflow_counter,strat_list,logger,\
                        log_dir)


    '''
    Inserting Scrubbing Workflow
    '''
    workflow_counter += 1
    strat_list = runScrubbing(c,subject_id,sub_dict,workflow,workflow_bit_id,\
                            workflow_counter,strat_list,logger,log_dir)


    '''
    Func -> Template, uses antsApplyTransforms (ANTS) or ApplyWarp (FSL) to
    apply the warp; also includes mean functional warp
    '''
    
    new_strat_list = []
    num_strat = 0
    if 1 in c.runRegisterFuncToMNI:

        for strat in strat_list:
            
            nodes = getNodeList(strat)
            
            # Run FSL ApplyWarp
            if 'anat_mni_fnirt_register' in nodes:

                func_mni_warp = pe.Node(interface=fsl.ApplyWarp(),
                                        name='func_mni_fsl_warp_%d' % num_strat)
                func_mni_warp.inputs.ref_file = c.template_brain_only_for_func
    
                functional_brain_mask_to_standard = pe.Node(interface=fsl.ApplyWarp(),
                                                            name='func_mni_fsl_warp_mask_%d' % num_strat)
                functional_brain_mask_to_standard.inputs.interp = 'nn'
                functional_brain_mask_to_standard.inputs.ref_file = c.template_skull_for_func

                mean_functional_warp = pe.Node(interface=fsl.ApplyWarp(), name='mean_func_fsl_warp_%d' % num_strat)
                mean_functional_warp.inputs.ref_file = c.template_brain_only_for_func
    
                try:

                    node, out_file = strat.get_node_from_resource_pool('anatomical_to_mni_nonlinear_xfm',logger)
                    workflow.connect(node, out_file,
                                     func_mni_warp, 'field_file')

                    node, out_file = strat.get_node_from_resource_pool('functional_to_anat_linear_xfm',logger)
                    workflow.connect(node, out_file,
                                     func_mni_warp, 'premat')
  
                    node, out_file = strat.get_leaf_properties()
                    workflow.connect(node, out_file,
                                     func_mni_warp, 'in_file')
    

                    node, out_file = strat.get_node_from_resource_pool('anatomical_to_mni_nonlinear_xfm',logger)
                    workflow.connect(node, out_file,
                                     functional_brain_mask_to_standard, 'field_file')
                    workflow.connect(node, out_file,
                                     mean_functional_warp, 'field_file')

                    node, out_file = strat.get_node_from_resource_pool('functional_to_anat_linear_xfm',logger)
                    workflow.connect(node, out_file,
                                     functional_brain_mask_to_standard, 'premat') 
                    workflow.connect(node, out_file,
                                     mean_functional_warp, 'premat') 

                    node, out_file = strat.get_node_from_resource_pool('functional_brain_mask',logger)
                    workflow.connect(node, out_file,
                                     functional_brain_mask_to_standard, 'in_file')

                    node, out_file = strat.get_node_from_resource_pool('mean_functional',logger)
                    workflow.connect(node, out_file, mean_functional_warp, 'in_file')

                    

                except:
                    logConnectionError('Functional Timeseries Registration to MNI space (FSL)', num_strat, strat.get_resource_pool(), '0015',logger)
                    raise
    
                strat.update_resource_pool({'functional_mni':(func_mni_warp, 'out_file'),
                                            'functional_brain_mask_to_standard':(functional_brain_mask_to_standard, 'out_file'),
                                            'mean_functional_in_mni':(mean_functional_warp, 'out_file')},logger)
                strat.append_name(func_mni_warp.name)
                create_log_node(workflow,func_mni_warp, 'out_file', num_strat,log_dir)
            
                num_strat += 1
                
                
        strat_list += new_strat_list  
            
        for strat in strat_list:
            
            nodes = getNodeList(strat)
             
            if ('ANTS' in c.regOption) and ('anat_mni_fnirt_register' not in nodes):
                # FUNCTIONAL apply warp
                fsl_to_itk_conversion('mean_functional', 'anatomical_brain', \
                    'functional_mni',num_strat,workflow,log_dir,strat)
                collect_transforms_func_mni('functional_mni',num_strat,workflow,log_dir,strat)

                node, out_file = strat.get_leaf_properties()
                ants_apply_warps_func_mni(node, out_file, \
                        c.template_brain_only_for_func, 'Linear', 3, \
                        'functional_mni',num_strat,workflow,log_dir,strat)

                # FUNCTIONAL MASK apply warp
                fsl_to_itk_conversion('functional_brain_mask', 'anatomical_brain', \
                'functional_brain_mask_to_standard',num_strat,workflow,log_dir,strat)
                collect_transforms_func_mni('functional_brain_mask_to_standard'\
                                ,num_strat,workflow,log_dir,strat)

                node, out_file = strat.get_node_from_resource_pool('func' \
                        'tional_brain_mask',logger)
                ants_apply_warps_func_mni(node, out_file, \
                    c.template_brain_only_for_func, 'NearestNeighbor', 0, \
                    'functional_brain_mask_to_standard',num_strat,workflow,log_dir,strat)

                # FUNCTIONAL MEAN apply warp
                fsl_to_itk_conversion('mean_functional', 'anatomical_brain', \
                                        'mean_functional_in_mni',num_strat,\
                                        workflow,log_dir,strat)
                collect_transforms_func_mni('mean_functional_in_mni',num_strat,\
                                workflow,log_dir,strat)

                node, out_file = strat.get_node_from_resource_pool('mean' \
                        '_functional',logger)
                ants_apply_warps_func_mni(node, out_file, \
                            c.template_brain_only_for_func, 'Linear', 0, \
                            'mean_functional_in_mni',num_strat,workflow,log_dir,strat)
                num_strat += 1


    strat_list += new_strat_list
    




    """""""""""""""""""""""""""""""""""""""""""""""""""
     OUTPUTS
    """""""""""""""""""""""""""""""""""""""""""""""""""
    
    '''
    Inserting VMHC Workflow
    '''
    strat_list = runVMHC(c,subject_id,sub_dict,workflow,workflow_bit_id,\
                            workflow_counter,strat_list,logger,log_dir)

    '''
    Inserting REHO Workflow
    '''
    strat_list = runReHo(c,subject_id,sub_dict,workflow,workflow_bit_id,\
                        workflow_counter,strat_list,logger,log_dir)

    '''
    Spatial Regression Based Time Series
    '''
    strat_list = runSpatialRegression(c,subject_id,sub_dict,workflow,\
                    workflow_bit_id,workflow_counter,strat_list,logger,log_dir)

    '''
    ROI Based Time Series
    '''

    new_strat_list = []
    num_strat = 0

    if 1 in c.runROITimeseries:

        for strat in strat_list:

            if c.roiSpecificationFile != None:

                resample_functional_to_roi = pe.Node(interface=fsl.FLIRT(),
                                                      name='resample_functional_to_roi_%d' % num_strat)
                resample_functional_to_roi.inputs.interp = 'trilinear'
                resample_functional_to_roi.inputs.apply_xfm = True
                resample_functional_to_roi.inputs.in_matrix_file = c.identityMatrix
    
                roi_dataflow = create_roi_mask_dataflow(c.roiSpecificationFile, 'ROI Average TSE', 'roi_dataflow_%d' % num_strat)
    
                roi_timeseries = get_roi_timeseries('roi_timeseries_%d' % num_strat)
                roi_timeseries.inputs.inputspec.output_type = c.roiTSOutputs
            
            
            if c.roiSpecificationFileForSCA != None:
            
                # same workflow, except to run TSE and send it to the resource pool
                # so that it will not get sent to SCA
                resample_functional_to_roi_for_sca = pe.Node(interface=fsl.FLIRT(),
                                                      name='resample_functional_to_roi_for_sca_%d' % num_strat)
                resample_functional_to_roi_for_sca.inputs.interp = 'trilinear'
                resample_functional_to_roi_for_sca.inputs.apply_xfm = True
                resample_functional_to_roi_for_sca.inputs.in_matrix_file = c.identityMatrix
                
                roi_dataflow_for_sca = create_roi_mask_dataflow(c.roiSpecificationFileForSCA, 'ROI Average TSE', 'roi_dataflow_for_sca_%d' % num_strat)
    
                roi_timeseries_for_sca = get_roi_timeseries('roi_timeseries_for_sca_%d' % num_strat)
                roi_timeseries_for_sca.inputs.inputspec.output_type = c.roiTSOutputs

            try:

                if c.roiSpecificationFile != None:

                    node, out_file = strat.get_node_from_resource_pool('functional_mni',logger)
    
                    # resample the input functional file to roi
                    workflow.connect(node, out_file,
                                     resample_functional_to_roi, 'in_file')
                    workflow.connect(roi_dataflow, 'outputspec.out_file',
                                     resample_functional_to_roi, 'reference')
    
                    # connect it to the roi_timeseries
                    workflow.connect(roi_dataflow, 'outputspec.out_file',
                                     roi_timeseries, 'input_roi.roi')
                    workflow.connect(resample_functional_to_roi, 'out_file',
                                     roi_timeseries, 'inputspec.rest')
                
                
                if c.roiSpecificationFileForSCA != None:
                    node, out_file = strat.get_node_from_resource_pool('functional_mni',logger)
                
                    # TSE only, not meant for SCA
                    # resample the input functional file to roi

                    workflow.connect(node, out_file,
                                     resample_functional_to_roi_for_sca, 'in_file')
                    workflow.connect(roi_dataflow_for_sca, 'outputspec.out_file',
                                     resample_functional_to_roi_for_sca, 'reference')
    
                    # connect it to the roi_timeseries
                    workflow.connect(roi_dataflow_for_sca, 'outputspec.out_file',
                                     roi_timeseries_for_sca, 'input_roi.roi')
                    workflow.connect(resample_functional_to_roi_for_sca, 'out_file',
                                     roi_timeseries_for_sca, 'inputspec.rest')

            except:
                logConnectionError('ROI Timeseries analysis', num_strat, strat.get_resource_pool(), '0031',logger)
                raise

            if 0 in c.runROITimeseries:
                tmp = strategy()
                tmp.resource_pool = dict(strat.resource_pool)
                tmp.leaf_node = (strat.leaf_node)
                tmp.leaf_out_file = str(strat.leaf_out_file)
                tmp.name = list(strat.name)
                strat = tmp
                new_strat_list.append(strat)

            if c.roiSpecificationFile != None:
                strat.append_name(roi_timeseries.name)
                strat.update_resource_pool({'roi_timeseries' : (roi_timeseries, 'outputspec.roi_outputs')},logger)
                create_log_node(workflow,roi_timeseries, 'outputspec.roi_outputs', num_strat,log_dir)


            if c.roiSpecificationFileForSCA != None:
                strat.append_name(roi_timeseries_for_sca.name)
                strat.update_resource_pool({'roi_timeseries_for_SCA' : \
                (roi_timeseries_for_sca, 'outputspec.roi_outputs')},logger)
                create_log_node(workflow,roi_timeseries_for_sca, 'outputspec.roi_outputs', num_strat,log_dir)

            if (c.roiSpecificationFile != None) or (c.roiSpecificationFileForSCA != None):
                num_strat += 1


    strat_list += new_strat_list



    '''
    Voxel Based Time Series 
    '''

    new_strat_list = []
    num_strat = 0
    if 1 in c.runVoxelTimeseries:


        for strat in strat_list:

            if c.maskSpecificationFile != None:

                resample_functional_to_mask = pe.Node(interface=fsl.FLIRT(),
                                                      name='resample_functional_to_mask_%d' % num_strat)
                resample_functional_to_mask.inputs.interp = 'trilinear'
                resample_functional_to_mask.inputs.apply_xfm = True
                resample_functional_to_mask.inputs.in_matrix_file = c.identityMatrix
    
                mask_dataflow = create_roi_mask_dataflow(c.maskSpecificationFile, 'ROI Voxelwise TSE', 'mask_dataflow_%d' % num_strat)
    
                voxel_timeseries = get_voxel_timeseries('voxel_timeseries_%d' % num_strat)
                voxel_timeseries.inputs.inputspec.output_type = c.voxelTSOutputs
            
            if c.maskSpecificationFileForSCA != None:
            
                resample_functional_to_mask_for_sca = pe.Node(interface=fsl.FLIRT(),
                                                      name='resample_functional_to_mask_for_sca_%d' % num_strat)
                resample_functional_to_mask_for_sca.inputs.interp = 'trilinear'
                resample_functional_to_mask_for_sca.inputs.apply_xfm = True
                resample_functional_to_mask_for_sca.inputs.in_matrix_file = c.identityMatrix
    
                mask_dataflow_for_sca = create_roi_mask_dataflow(c.maskSpecificationFileForSCA, 'ROI Voxelwise TSE', 'mask_dataflow_for_sca_%d' % num_strat)
    
                voxel_timeseries_for_sca = get_voxel_timeseries('voxel_timeseries_for_sca_%d' % num_strat)
                voxel_timeseries_for_sca.inputs.inputspec.output_type = c.voxelTSOutputs
            

            try:

                if c.maskSpecificationFile != None:

                    node, out_file = \
                    strat.get_node_from_resource_pool('functional_mni',logger)
    
                    # resample the input functional file to mask
                    workflow.connect(node, out_file,
                                     resample_functional_to_mask, 'in_file')
                    workflow.connect(mask_dataflow, 'outputspec.out_file',
                                     resample_functional_to_mask, 'reference')
    
                    # connect it to the voxel_timeseries
                    workflow.connect(mask_dataflow, 'outputspec.out_file',
                                     voxel_timeseries, 'input_mask.mask')
                    workflow.connect(resample_functional_to_mask, 'out_file',
                                     voxel_timeseries, 'inputspec.rest')
                
                if c.maskSpecificationFileForSCA != None:
                    
                    node, out_file = strat.get_node_from_resource_pool('functional_mni',logger)
                    
                    # resample the input functional file to mask
                    workflow.connect(node, out_file,
                                     resample_functional_to_mask_for_sca, 'in_file')
                    workflow.connect(mask_dataflow_for_sca, 'outputspec.out_file',
                                     resample_functional_to_mask_for_sca, 'reference')
    
                    # connect it to the voxel_timeseries
                    workflow.connect(mask_dataflow_for_sca, 'outputspec.out_file',
                                     voxel_timeseries_for_sca, 'input_mask.mask')
                    workflow.connect(resample_functional_to_mask_for_sca, 'out_file',
                                     voxel_timeseries_for_sca, 'inputspec.rest')
                

            except:
                logConnectionError('Voxel timeseries analysis', num_strat, strat.get_resource_pool(), '0030',logger)

                raise

            if 0 in c.runVoxelTimeseries:
                tmp = strategy()
                tmp.resource_pool = dict(strat.resource_pool)
                tmp.leaf_node = (strat.leaf_node)
                tmp.leaf_out_file = str(strat.leaf_out_file)
                tmp.name = list(strat.name)
                strat = tmp
                new_strat_list.append(strat)

            if c.maskSpecificationFile != None:
                strat.append_name(voxel_timeseries.name)
                strat.update_resource_pool({'voxel_timeseries': (voxel_timeseries, 'outputspec.mask_outputs')},logger)
                create_log_node(workflow,voxel_timeseries, 'outputspec.mask_outputs', num_strat,log_dir)


            if c.maskSpecificationFileForSCA != None:
                strat.append_name(voxel_timeseries_for_sca.name)
                strat.update_resource_pool({'voxel_timeseries_for_SCA':\
                 (voxel_timeseries_for_sca, 'outputspec.mask_outputs')},logger)
                create_log_node(workflow,voxel_timeseries_for_sca, 'outputspec.mask_outputs', num_strat,log_dir)

            if (c.maskSpecificationFile != None) or (c.maskSpecificationFileForSCA != None):
                num_strat += 1
    strat_list += new_strat_list




    '''
    Inserting SCA Workflow for ROI INPUT
    '''
    strat_list = runSCAforROIinput(c,subject_id,sub_dict,workflow,workflow_bit_id,\
                        workflow_counter,strat_list,logger,log_dir)
    

    '''
    Inserting SCA
    Workflow for Voxel INPUT
    '''

    new_strat_list = []
    num_strat = 0

    if 1 in c.runSCA and (1 in c.runVoxelTimeseries):
        for strat in strat_list:

            sca_seed = create_sca('sca_seed_%d' % num_strat)


            try:
                node, out_file = strat.get_leaf_properties()
                workflow.connect(node, out_file,
                                 sca_seed, 'inputspec.functional_file')

                node, out_file = strat.get_node_from_resource_pool('voxel_timeseries_for_SCA',logger)
                workflow.connect(node, (out_file, extract_one_d),
                                 sca_seed, 'inputspec.timeseries_one_d')
            except:
                logConnectionError('SCA', num_strat, strat.get_resource_pool(), '0036',logger)
                raise



            strat.update_resource_pool({'sca_seed_correlations':(sca_seed, 'outputspec.correlation_file')},logger)
            #strat.update_resource_pool({'sca_seed_Z':(sca_seed, 'outputspec.Z_score')})

            strat.append_name(sca_seed.name)
            num_strat += 1
    strat_list += new_strat_list



    '''
    Temporal Regression for Dual Regression
    '''

    new_strat_list = []
    num_strat = 0

    if 1 in c.runDualReg and (1 in c.runSpatialRegression):
        for strat in strat_list:

            dr_temp_reg = create_temporal_reg('temporal_dual_regression_%d' % num_strat)
            dr_temp_reg.inputs.inputspec.normalize = c.mrsNorm
            dr_temp_reg.inputs.inputspec.demean = c.mrsDemean

            try:
                node, out_file = strat.get_node_from_resource_pool('spatial_map_timeseries',logger)
                
                node2, out_file2 = strat.get_leaf_properties()
                node3, out_file3 = strat.get_node_from_resource_pool('functional_brain_mask',logger)

                workflow.connect(node2, out_file2,
                                 dr_temp_reg, 'inputspec.subject_rest')

                workflow.connect(node, out_file,
                                 dr_temp_reg, 'inputspec.subject_timeseries')
       
                workflow.connect(node3, out_file3,dr_temp_reg, 'inputspec.subject_mask')

            except:
                logConnectionError('Temporal multiple regression for dual regression', \
                        num_strat, strat.get_resource_pool(), '0033',logger)
                raise


            strat.update_resource_pool({'dr_tempreg_maps_stack':(dr_temp_reg, 'outputspec.temp_reg_map'),
                                        'dr_tempreg_maps_files':(dr_temp_reg, 'outputspec.temp_reg_map_files')},logger)
            strat.update_resource_pool({'dr_tempreg_maps_zstat_stack':(dr_temp_reg, 'outputspec.temp_reg_map_z'),
                                        'dr_tempreg_maps_zstat_files':(dr_temp_reg, 'outputspec.temp_reg_map_z_files')},logger)

            strat.append_name(dr_temp_reg.name)
            
            create_log_node(workflow,dr_temp_reg, 'outputspec.temp_reg_map', num_strat,log_dir)
            
            num_strat += 1
            
    elif 1 in c.runDualReg and (0 in c.runSpatialRegression):
        logger.info("\n\n" + "WARNING: Dual Regression - Spatial regression was turned off for at least one of the strategies.")
        logger.info("Spatial regression is required for dual regression." + "\n\n")
            
    strat_list += new_strat_list



    '''
    Temporal Regression for SCA
    '''

    new_strat_list = []
    num_strat = 0

    if 1 in c.runMultRegSCA and (1 in c.runROITimeseries):
        for strat in strat_list:

            sc_temp_reg = create_temporal_reg('temporal_regression_sca_%d' % num_strat, which='RT')
            sc_temp_reg.inputs.inputspec.normalize = c.mrsNorm
            sc_temp_reg.inputs.inputspec.demean = c.mrsDemean

            try:
                node, out_file = strat.get_node_from_resource_pool('functional_mni',logger)
                node2, out_file2 = strat.get_node_from_resource_pool('roi_timeseries_for_SCA',logger)
                node3, out_file3 = strat.get_node_from_resource_pool('functional_brain_mask_to_standard',logger)

                workflow.connect(node, out_file,
                                 sc_temp_reg, 'inputspec.subject_rest')

                workflow.connect(node2, (out_file2, extract_txt),
                                 sc_temp_reg, 'inputspec.subject_timeseries')

                workflow.connect(node3, out_file3,
                                 sc_temp_reg, 'inputspec.subject_mask')

            except:
                logConnectionError('Temporal multiple regression'+\
                ' for seed based connectivity', num_strat, \
                strat.get_resource_pool(), '0037',logger)
                raise



            strat.update_resource_pool({'sca_tempreg_maps_stack':(sc_temp_reg, 'outputspec.temp_reg_map'),
                                        'sca_tempreg_maps_files':(sc_temp_reg, 'outputspec.temp_reg_map_files')},logger)
            strat.update_resource_pool({'sca_tempreg_maps_zstat_stack':(sc_temp_reg, 'outputspec.temp_reg_map_z'),
                                        'sca_tempreg_maps_zstat_files':(sc_temp_reg, 'outputspec.temp_reg_map_z_files')},logger)

            
            create_log_node(workflow,sc_temp_reg, 'outputspec.temp_reg_map', num_strat,log_dir)
            
            strat.append_name(sc_temp_reg.name)
            num_strat += 1
    strat_list += new_strat_list



    '''
    Inserting Surface Registration
    '''

    new_strat_list = []
    num_strat = 0

    workflow_counter += 1
    if 1 in c.runSurfaceRegistraion:
        workflow_bit_id['surface_registration'] = workflow_counter
        for strat in strat_list:

            surface_reg = create_surface_registration('surface_reg_%d' % num_strat)
            surface_reg.inputs.inputspec.recon_subjects = c.reconSubjectsDirectory
            surface_reg.inputs.inputspec.subject_id = subject_id


            try:

                node, out_file = strat.get_leaf_properties()
                workflow.connect(node, out_file,
                                 surface_reg, 'inputspec.rest')

                node, out_file = strat.get_node_from_resource_pool('anatomical_brain',logger)
                workflow.connect(node, out_file,
                                 surface_reg, 'inputspec.brain')

            except:
                logConnectionError('Surface Registration Workflow', \
                num_strat, strat.get_resource_pool(), '0048',logger)
                raise

            if 0 in c.runSurfaceRegistraion:
                tmp = strategy()
                tmp.resource_pool = dict(strat.resource_pool)
                tmp.leaf_node = (strat.leaf_node)
                tmp.leaf_out_file = str(strat.leaf_out_file)
                tmp.name = list(strat.name)
                strat = tmp
                new_strat_list.append(strat)

            strat.append_name(surface_reg.name)

            strat.update_resource_pool({'bbregister_registration' : (surface_reg, 'outputspec.out_reg_file'),
                                        'left_hemisphere_surface' :  (surface_reg, 'outputspec.lh_surface_file'),
                                        'right_hemisphere_surface' : (surface_reg, 'outputspec.rh_surface_file')},logger)

            num_strat += 1

    strat_list += new_strat_list



    '''
    Inserting vertices based timeseries
    '''

    new_strat_list = []
    num_strat = 0

    if 1 in c.runVerticesTimeSeries:
        for strat in strat_list:

            vertices_timeseries = get_vertices_timeseries('vertices_timeseries_%d' % num_strat)

            try:

                node, out_file = strat.get_node_from_resource_pool('left_hemisphere_surface',logger)
                workflow.connect(node, out_file,
                                 vertices_timeseries, 'inputspec.lh_surface_file')

                node, out_file = strat.get_node_from_resource_pool('right_hemisphere_surface',logger)
                workflow.connect(node, out_file,
                                 vertices_timeseries, 'inputspec.rh_surface_file')

            except:
                logConnectionError('Vertices Timeseries Extraction', \
                    num_strat, strat.get_resource_pool(), '0049',logger)
                raise

            if 0 in c.runVerticesTimeSeries:
                tmp = strategy()
                tmp.resource_pool = dict(strat.resource_pool)
                tmp.leaf_node = (strat.leaf_node)
                tmp.leaf_out_file = str(strat.leaf_out_file)
                tmp.name = list(strat.name)
                strat = tmp
                new_strat_list.append(strat)

            strat.append_name(vertices_timeseries.name)

            strat.update_resource_pool({'vertices_timeseries' : \
                (vertices_timeseries, 'outputspec.surface_outputs')},logger)

            num_strat += 1

    strat_list += new_strat_list



    inputnode_fwhm = None
    if c.fwhm != None:

        inputnode_fwhm = pe.Node(util.IdentityInterface(fields=['fwhm']),
                             name='fwhm_input')
        inputnode_fwhm.iterables = ("fwhm", c.fwhm)

    '''
    Inserting Network centrality
    '''

    new_strat_list = []
    num_strat = 0


    if 1 in c.runNetworkCentrality:
        # For each desired strategy
        for strat in strat_list:
            
            # Resample the functional mni to the centrality mask resolution
            resample_functional_to_template = pe.Node(interface=fsl.FLIRT(),
                                                  name='resample_functional_to_template_%d' % num_strat)
            resample_functional_to_template.inputs.interp = 'trilinear'
            resample_functional_to_template.inputs.apply_xfm = True
            resample_functional_to_template.inputs.in_matrix_file = c.identityMatrix

            template_dataflow = create_roi_mask_dataflow(c.templateSpecificationFile, 'Network Centrality', 'template_dataflow_%d' % num_strat)

            # Connect in each workflow for the centrality method of interest
            
                
            # Init merge node for appending method output lists to one another
            merge_node = pe.Node(util.Function(input_names=['deg_list',
                                                            'eig_list',
                                                            'lfcd_list'],
                                          output_names = ['merged_list'],
                                          function = merge_lists),
                            name = 'merge_node_%d' % num_strat)
            
            # If we're calculating degree centrality
            if c.degWeightOptions.count(True) > 0:
                connectCentralityWorkflow(0,c.degCorrelationThresholdOption,\
                                          c.degCorrelationThreshold,c.degWeightOptions,\
                                          'deg_list',workflow,log_dir,num_strat)

            # If we're calculating eigenvector centrality
            if c.eigWeightOptions.count(True) > 0:
                connectCentralityWorkflow(1,c.eigCorrelationThresholdOption,
                                          c.eigCorrelationThreshold,c.eigWeightOptions,
                                          'eig_list',workflow,log_dir,num_strat)
            
            # If we're calculating lFCD
            if c.lfcdWeightOptions.count(True) > 0:
                connectCentralityWorkflow(2,2,c.lfcdCorrelationThreshold,\
                                          c.lfcdWeightOptions,'lfcd_list',workflow,log_dir,num_strat)

            try:

                node, out_file = strat.get_node_from_resource_pool('functional_mni',logger)

                # resample the input functional file to template(roi/mask)
                workflow.connect(node, out_file,
                                 resample_functional_to_template, 'in_file')
                workflow.connect(template_dataflow, 'outputspec.out_file',
                                 resample_functional_to_template, 'reference')
                strat.update_resource_pool({'centrality_outputs' : (merge_node, 'merged_list')},logger)

                # if smoothing is required
                if c.fwhm != None :

                    z_score = get_cent_zscore('centrality_zscore_%d' % num_strat)

                    smoothing = pe.MapNode(interface=fsl.MultiImageMaths(),
                                       name='network_centrality_smooth_%d' % num_strat,
                                       iterfield=['in_file'])


                    # calculate zscores
                    workflow.connect(template_dataflow, 'outputspec.out_file',
                                     z_score, 'inputspec.mask_file')
# workflow.connect(network_centrality, 'outputspec.centrality_outputs',
# z_score, 'inputspec.input_file')
                    workflow.connect(merge_node, 'merged_list',
                                     z_score, 'inputspec.input_file')


                    # connecting zscores to smoothing
                    workflow.connect(template_dataflow, 'outputspec.out_file',
                                     smoothing, 'operand_files')
                    workflow.connect(z_score, 'outputspec.z_score_img',
                                    smoothing, 'in_file')
                    workflow.connect(inputnode_fwhm, ('fwhm', set_gauss),
                                     smoothing, 'op_string')

                    strat.append_name(smoothing.name)
                    strat.update_resource_pool({'centrality_outputs_smoothed' : (smoothing, 'out_file'),
                                                'centrality_outputs_zscore' : (z_score, 'outputspec.z_score_img')},logger)
                    
                    strat.append_name(smoothing.name)
                    create_log_node(workflow,smoothing, 'out_file', num_strat,log_dir)

            except:
                logConnectionError('Network Centrality', num_strat, strat.get_resource_pool(), '0050',logger)
                raise

            if 0 in c.runNetworkCentrality:
                tmp = strategy()
                tmp.resource_pool = dict(strat.resource_pool)
                tmp.leaf_node = (strat.leaf_node)
                tmp.leaf_out_file = str(strat.leaf_out_file)
                tmp.name = list(strat.name)
                strat = tmp
                new_strat_list.append(strat)
            num_strat += 1
    strat_list += new_strat_list
    num_strat = 0





    """""""""""""""""""""""""""""""""""""""""""""""""""
     WARP OUTPUTS TO TEMPLATE
    """""""""""""""""""""""""""""""""""""""""""""""""""

    '''
    Transforming Dual Regression outputs to MNI
    '''
    new_strat_list = []
    num_strat = 0
    if (1 in c.runRegisterFuncToMNI) and (1 in c.runDualReg) and (1 in c.runSpatialRegression):
        for strat in strat_list:
            num_strat = output_to_standard(c,workflow,logger,'dr_tempreg_maps_stack', 'dr_tempreg_maps_stack', strat, num_strat)
            num_strat = output_to_standard(c,workflow,logger,'dr_tempreg_maps_zstat_stack', 'dr_tempreg_maps_zstat_stack', strat, num_strat)
            num_strat = output_to_standard(c,workflow,logger,'dr_tempreg_maps_files', 'dr_tempreg_maps_files', strat, num_strat, 1)
            num_strat = output_to_standard(c,workflow,logger,'dr_tempreg_maps_zstat_files', 'dr_tempreg_maps_zstat_files', strat, num_strat, 1)
            num_strat += 1    
    strat_list += new_strat_list

    '''
    Transforming alff/falff outputs to MNI
    '''
    new_strat_list = []
    num_strat = 0
    if 1 in c.runRegisterFuncToMNI and (1 in c.runALFF):
        for strat in strat_list:
            num_strat = output_to_standard(c,workflow,logger,'alff', 'alff_img', strat, num_strat)
            num_strat = output_to_standard(c,workflow,logger,'falff', 'falff_img', strat, num_strat)               
            num_strat += 1    
    strat_list += new_strat_list

    '''
    Transforming ReHo outputs to MNI
    '''    
    new_strat_list = []
    num_strat = 0
    if 1 in c.runRegisterFuncToMNI and (1 in c.runReHo):
        for strat in strat_list:
            num_strat = output_to_standard(c,workflow,logger,'reho', 'raw_reho_map', strat, num_strat)
            num_strat += 1
    strat_list += new_strat_list


    '''
    Transforming SCA ROI outputs to MNI
    '''
    new_strat_list = []
    num_strat = 0
    if 1 in c.runRegisterFuncToMNI and (1 in c.runSCA) and (1 in c.runROITimeseries):
        for strat in strat_list:
            num_strat = output_to_standard(c,workflow,logger,'sca_roi', 'sca_roi_correlations', strat, num_strat)            
            num_strat += 1
    strat_list += new_strat_list


    '''
    Transforming SCA Voxel outputs to MNI
    '''
    new_strat_list = []
    num_strat = 0
    if 1 in c.runRegisterFuncToMNI and (1 in c.runSCA) and (1 in c.runVoxelTimeseries):
        for strat in strat_list:
            num_strat = output_to_standard(c,workflow,logger,'sca_seed', 'sca_seed_correlations', strat, num_strat)            
            num_strat += 1    
    strat_list += new_strat_list


    """""""""""""""""""""""""""""""""""""""""""""""""""
     SMOOTHING NORMALIZED OUTPUTS
    """""""""""""""""""""""""""""""""""""""""""""""""""

    '''
    Smoothing Temporal Regression for SCA scores
    '''
    new_strat_list = []
    num_strat = 0
    if (1 in c.runMultRegSCA) and (1 in c.runROITimeseries) and c.fwhm != None:
        for strat in strat_list:

            sc_temp_reg_maps_smooth = pe.MapNode(interface=fsl.MultiImageMaths(),\
                                              name='sca_tempreg_maps_stack_smooth_%d' % num_strat, iterfield=['in_file'])
            sc_temp_reg_maps_files_smooth = pe.MapNode(interface=fsl.MultiImageMaths(),\
                                              name='sca_tempreg_maps_files_smooth_%d' % num_strat, iterfield=['in_file'])
            sc_temp_reg_maps_Z_stack_smooth = pe.MapNode(interface=fsl.MultiImageMaths(),
                                              name='sca_tempreg_maps_Z_stack_smooth_%d' % \
                                            num_strat, iterfield=['in_file'])
            sc_temp_reg_maps_Z_files_smooth = pe.MapNode(interface=fsl.MultiImageMaths(),
                                              name='sca_tempreg_maps_Z_files_smooth_%d' % \
                                            num_strat, iterfield=['in_file'])

            try:

                node, out_file = strat.get_node_from_resource_pool('sca_tempreg_maps_stack',logger)
                node5, out_file5 = strat.get_node_from_resource_pool('sca_tempreg_maps_files',logger)
                node2, out_file2 = strat.get_node_from_resource_pool('sca_tempreg_maps_zstat_stack',logger)
                node3, out_file3 = strat.get_node_from_resource_pool('sca_tempreg_maps_zstat_files',logger)
                node4, out_file4 = strat.get_node_from_resource_pool('functional_brain_mask_to_standard',logger)


                # non-normalized stack
                workflow.connect(node, out_file,
                                 sc_temp_reg_maps_smooth, 'in_file')
                workflow.connect(inputnode_fwhm, ('fwhm', set_gauss),
                                 sc_temp_reg_maps_smooth, 'op_string')

                workflow.connect(node4, out_file4,
                                 sc_temp_reg_maps_smooth, 'operand_files')

                # non-normalized files
                workflow.connect(node5, out_file5,
                                 sc_temp_reg_maps_files_smooth, 'in_file')
                workflow.connect(inputnode_fwhm, ('fwhm', set_gauss),
                                 sc_temp_reg_maps_files_smooth, 'op_string')

                workflow.connect(node4, out_file4,
                                 sc_temp_reg_maps_files_smooth, 'operand_files')

                # normalized stack
                workflow.connect(node2, out_file2,
                                 sc_temp_reg_maps_Z_stack_smooth, 'in_file')
                workflow.connect(inputnode_fwhm, ('fwhm', set_gauss),
                                 sc_temp_reg_maps_Z_stack_smooth, 'op_string')

                workflow.connect(node4, out_file4,
                                 sc_temp_reg_maps_Z_stack_smooth, 'operand_files')

                # normalized files
                workflow.connect(node3, out_file3,
                                 sc_temp_reg_maps_Z_files_smooth, 'in_file')
                workflow.connect(inputnode_fwhm, ('fwhm', set_gauss),
                                 sc_temp_reg_maps_Z_files_smooth, 'op_string')

                workflow.connect(node4, out_file4,
                                 sc_temp_reg_maps_Z_files_smooth, 'operand_files')

            except:
                logConnectionError('SCA Temporal regression smooth', \
                        num_strat, strat.get_resource_pool(), '0038',logger)
                raise
            strat.append_name(sc_temp_reg_maps_smooth.name)

            strat.update_resource_pool({'sca_tempreg_maps_stack_smooth':(sc_temp_reg_maps_smooth, 'out_file'),
                                        'sca_tempreg_maps_files_smooth':(sc_temp_reg_maps_files_smooth, 'out_file'),
                                        'sca_tempreg_maps_zstat_stack_smooth':(sc_temp_reg_maps_Z_stack_smooth, 'out_file'),
                                        'sca_tempreg_maps_zstat_files_smooth':(sc_temp_reg_maps_Z_files_smooth, 'out_file')},logger)

            create_log_node(workflow,sc_temp_reg_maps_smooth, 'out_file', num_strat,log_dir)
            num_strat += 1
    strat_list += new_strat_list



    '''
    Smoothing Temporal Regression for Dual Regression
    '''
    new_strat_list = []
    num_strat = 0

    if (1 in c.runDualReg) and (1 in c.runSpatialRegression) and c.fwhm != None:
        for strat in strat_list:

            dr_temp_reg_maps_smooth = pe.Node(interface=fsl.MultiImageMaths(),
                                              name='dr_tempreg_maps_stack_smooth_%d' % num_strat)
            dr_temp_reg_maps_Z_stack_smooth = pe.Node(interface=fsl.MultiImageMaths(),
                                              name='dr_tempreg_maps_Z_stack_smooth_%d' % num_strat)
            dr_temp_reg_maps_files_smooth = pe.MapNode(interface=fsl.MultiImageMaths(),
                                              name='dr_tempreg_maps_files_smooth_%d' % num_strat, iterfield=['in_file'])
            dr_temp_reg_maps_Z_files_smooth = pe.MapNode(interface=fsl.MultiImageMaths(),
                                              name='dr_tempreg_maps_Z_files_smooth_%d' % num_strat, iterfield=['in_file'])

            try:

                node, out_file = strat.get_node_from_resource_pool('dr_tempreg_maps_stack_to_standard',logger)
                node2, out_file2 = strat.get_node_from_resource_pool('dr_tempreg_maps_zstat_stack_to_standard',logger)
                node5, out_file5 = strat.get_node_from_resource_pool('dr_tempreg_maps_files_to_standard',logger)
                node3, out_file3 = strat.get_node_from_resource_pool('dr_tempreg_maps_zstat_files_to_standard',logger)
                node4, out_file4 = strat.get_node_from_resource_pool('functional_brain_mask_to_standard',logger)


                # non-normalized stack
                workflow.connect(node, out_file,
                                 dr_temp_reg_maps_smooth, 'in_file')
                workflow.connect(inputnode_fwhm, ('fwhm', set_gauss),
                                 dr_temp_reg_maps_smooth, 'op_string')

                workflow.connect(node4, out_file4,
                                 dr_temp_reg_maps_smooth, 'operand_files')

                # normalized stack
                workflow.connect(node2, out_file2,
                                 dr_temp_reg_maps_Z_stack_smooth, 'in_file')
                workflow.connect(inputnode_fwhm, ('fwhm', set_gauss),
                                 dr_temp_reg_maps_Z_stack_smooth, 'op_string')

                workflow.connect(node4, out_file4,
                                 dr_temp_reg_maps_Z_stack_smooth, 'operand_files')

                # normalized files
                workflow.connect(node5, out_file5,
                                 dr_temp_reg_maps_files_smooth, 'in_file')
                workflow.connect(inputnode_fwhm, ('fwhm', set_gauss),
                                 dr_temp_reg_maps_files_smooth, 'op_string')

                workflow.connect(node4, out_file4,
                                 dr_temp_reg_maps_files_smooth, 'operand_files')

                # normalized z-stat files
                workflow.connect(node3, out_file3,
                                 dr_temp_reg_maps_Z_files_smooth, 'in_file')
                workflow.connect(inputnode_fwhm, ('fwhm', set_gauss),
                                 dr_temp_reg_maps_Z_files_smooth, 'op_string')

                workflow.connect(node4, out_file4,
                                 dr_temp_reg_maps_Z_files_smooth, 'operand_files')

            except:
                logConnectionError('Dual regression temp reg smooth', \
                    num_strat, strat.get_resource_pool(), '0039',logger)
                raise
            strat.append_name(dr_temp_reg_maps_smooth.name)
            strat.update_resource_pool({\
                'dr_tempreg_maps_stack_smooth':(dr_temp_reg_maps_smooth, 'out_file'),
                'dr_tempreg_maps_zstat_stack_smooth':(dr_temp_reg_maps_Z_stack_smooth, 'out_file'),
                'dr_tempreg_maps_files_smooth':(dr_temp_reg_maps_files_smooth, 'out_file'),
                'dr_tempreg_maps_zstat_files_smooth':(dr_temp_reg_maps_Z_files_smooth, 'out_file')},\
                logger)
            create_log_node(workflow,dr_temp_reg_maps_smooth, 'out_file', num_strat,log_dir)

            num_strat += 1
    strat_list += new_strat_list



    '''    
    Smoothing ALFF fALFF Z scores and or possibly Z scores in MNI 
    '''
    new_strat_list = []
    num_strat = 0
    if (1 in c.runALFF) and c.fwhm != None:
        for strat in strat_list:
            num_strat=output_smooth(workflow,inputnode_fwhm,'alff', 'alff_img', strat, num_strat,logger,c,log_dir)
            num_strat=output_smooth(workflow,inputnode_fwhm,'falff', 'falff_img', strat, num_strat,logger,c,log_dir)
            num_strat += 1
    strat_list += new_strat_list

    '''
    z-standardize alff/falff MNI-standardized outputs
    '''
    new_strat_list = []
    num_strat = 0
    if 1 in c.runZScoring and (1 in c.runALFF):
        for strat in strat_list:
            if c.fwhm != None:
                z_score_standardize(workflow,'alff', 'alff_to_standard_smooth', strat, num_strat,logger)
                z_score_standardize(workflow,'falff', 'falff_to_standard_smooth', strat, num_strat,logger)
            else:
                z_score_standardize(workflow,'alff', 'alff_to_standard', strat, num_strat,logger)
                z_score_standardize(workflow,'falff', 'falff_to_standard', strat, num_strat,logger)
            num_strat += 1
    strat_list += new_strat_list

    '''
    Smoothing ReHo outputs and or possibly ReHo outputs in MNI 
    '''    
    new_strat_list = []
    num_strat = 0
    if (1 in c.runReHo) and c.fwhm != None:
        for strat in strat_list:
            num_strat=output_smooth(workflow,inputnode_fwhm,'reho', 'raw_reho_map', strat, num_strat,logger,c,log_dir)
            num_strat += 1
    strat_list += new_strat_list

    '''
    z-standardize ReHo MNI-standardized outputs
    '''
    new_strat_list = []
    num_strat = 0
    if 1 in c.runZScoring and (1 in c.runReHo):
        for strat in strat_list:
            if c.fwhm != None:
                z_score_standardize(workflow,'reho', 'reho_to_standard_smooth', strat, num_strat,logger)
            else:
                z_score_standardize(workflow,'reho', 'reho_to_standard', strat, num_strat,logger)
                num_strat += 1
    strat_list += new_strat_list

    '''
    Smoothing SCA roi based Z scores and or possibly Z scores in MNI 
    '''
    if (1 in c.runSCA) and (1 in c.runROITimeseries) and c.fwhm != None:
        for strat in strat_list:
            num_strat=output_smooth(workflow,inputnode_fwhm,'sca_roi', 'sca_roi_correlations', strat, num_strat,logger,c,log_dir)            
            num_strat += 1
    strat_list += new_strat_list

    '''
    fisher-z-standardize SCA ROI MNI-standardized outputs
    '''
    new_strat_list = []
    num_strat = 0
    if 1 in c.runZScoring and (1 in c.runSCA) and (1 in c.runROITimeseries):
        for strat in strat_list:
            if c.fwhm != None:
                fisher_z_score_standardize(workflow,'sca_roi', 'sca_roi_to_standard_smooth', 'roi_timeseries_for_SCA', strat, num_strat,logger, 1)
            else:
                fisher_z_score_standardize(workflow,'sca_roi', 'sca_roi_to_standard', 'roi_timeseries_for_SCA', strat, num_strat,logger, 1)
            num_strat += 1
    strat_list += new_strat_list

    '''
    Smoothing SCA seed based Z scores and or possibly Z scores in MNI 
    '''
    new_strat_list = []
    num_strat = 0
    if (1 in c.runSCA) and (1 in c.runVoxelTimeseries) and c.fwhm != None:
        for strat in strat_list:
            num_strat=output_smooth(workflow,inputnode_fwhm,'sca_seed', 'sca_seed_correlations', strat, num_strat,logger,c,log_dir)
            num_strat += 1
    strat_list += new_strat_list


    '''
    fisher-z-standardize SCA seed MNI-standardized outputs
    '''
    new_strat_list = []
    num_strat = 0
    if 1 in c.runZScoring and (1 in c.runSCA) and (1 in c.runVoxelTimeseries):
        for strat in strat_list:
            if c.fwhm != None:
                fisher_z_score_standardize(workflow,'sca_seed', 'sca_seed_to_standard_smooth', 'voxel_timeseries_for_SCA', strat, num_strat,logger, 1)
            else:
                fisher_z_score_standardize(workflow,'sca_seed', 'sca_seed_to_standard', 'voxel_timeseries_for_SCA', strat, num_strat,logger, 1)
            num_strat += 1
    strat_list += new_strat_list





    """""""""""""""""""""""""""""""""""""""""""""""""""
     QUALITY CONTROL
    """""""""""""""""""""""""""""""""""""""""""""""""""


    if 1 in c.generateQualityControlImages:

        #register color palettes
        register_pallete(os.path.realpath(
                os.path.join(CPAC.__path__[0], 'qc', 'red.py')), 'red')
        register_pallete(os.path.realpath(
                os.path.join(CPAC.__path__[0], 'qc', 'green.py')), 'green')
        register_pallete(os.path.realpath(
                os.path.join(CPAC.__path__[0], 'qc', 'blue.py')), 'blue')
        register_pallete(os.path.realpath(
                os.path.join(CPAC.__path__[0], 'qc', 'red_to_blue.py')), 'red_to_blue')
        register_pallete(os.path.realpath(
                os.path.join(CPAC.__path__[0], 'qc', 'cyan_to_yellow.py')), 'cyan_to_yellow')
    
        hist = pe.Node(util.Function(input_names=['measure_file',
                                                   'measure'],
                                     output_names=['hist_path'],
                                     function=gen_histogram),
                        name='histogram')

        for strat in strat_list:

            nodes = getNodeList(strat)

            #make SNR plot

            if 1 in c.runFunctionalPreprocessing:

                try:

                    hist_ = hist.clone('hist_snr_%d' % num_strat)
                    hist_.inputs.measure = 'snr'

                    drop_percent = pe.Node(util.Function(input_names=['measure_file',
                                                     'percent_'],
                                       output_names=['modified_measure_file'],
                                       function=drop_percent_),
                                       name='dp_snr_%d' % num_strat)
                    drop_percent.inputs.percent_ = 99

                    preproc, out_file = strat.get_node_from_resource_pool('preprocessed',logger)
                    brain_mask, mask_file = strat.get_node_from_resource_pool('functional_brain_mask',logger)
                    func_to_anat_xfm, xfm_file = strat.get_node_from_resource_pool('functional_to_anat_linear_xfm',logger)
                    anat_ref, ref_file = strat.get_node_from_resource_pool('anatomical_brain',logger)
                    mfa, mfa_file = strat.get_node_from_resource_pool('mean_functional_in_anat',logger)

                    std_dev = pe.Node(util.Function(input_names=['mask_', 'func_'],
                                                    output_names=['new_fname'],
                                                      function=gen_std_dev),
                                        name='std_dev_%d' % num_strat)

                    std_dev_anat = pe.Node(util.Function(input_names=['func_',
                                                                      'ref_',
                                                                      'xfm_',
                                                                      'interp_'],
                                                         output_names=['new_fname'],
                                                         function=gen_func_anat_xfm),
                                           name='std_dev_anat_%d' % num_strat)

                    snr = pe.Node(util.Function(input_names=['std_dev', 'mean_func_anat'],
                                                output_names=['new_fname'],
                                                function=gen_snr),
                                  name='snr_%d' % num_strat)

                    ###
                    snr_val = pe.Node(util.Function(input_names=['measure_file'],
                                                output_names=['snr_storefl'],
                                                function=cal_snr_val),
                                  name='snr_val%d' % num_strat)


                    std_dev_anat.inputs.interp_ = 'trilinear'

                    montage_snr = create_montage('montage_snr_%d' % num_strat,
                                    'red_to_blue', 'snr')


                    workflow.connect(preproc, out_file,
                                     std_dev, 'func_')

                    workflow.connect(brain_mask, mask_file,
                                     std_dev, 'mask_')

                    workflow.connect(std_dev, 'new_fname',
                                     std_dev_anat, 'func_')

                    workflow.connect(func_to_anat_xfm, xfm_file,
                                     std_dev_anat, 'xfm_')

                    workflow.connect(anat_ref, ref_file,
                                     std_dev_anat, 'ref_')

                    workflow.connect(std_dev_anat, 'new_fname',
                                     snr, 'std_dev')

                    workflow.connect(mfa, mfa_file,
                                     snr, 'mean_func_anat')

                    workflow.connect(snr, 'new_fname',
                                     hist_, 'measure_file')

                    workflow.connect(snr, 'new_fname',
                                     drop_percent, 'measure_file')

                    workflow.connect(snr, 'new_fname',
                                     snr_val, 'measure_file')   ###


                    workflow.connect(drop_percent, 'modified_measure_file',
                                     montage_snr, 'inputspec.overlay')

                    workflow.connect(anat_ref, ref_file,
                                    montage_snr, 'inputspec.underlay')


                    strat.update_resource_pool({'qc___snr_a': (montage_snr, 'outputspec.axial_png'),
                                                'qc___snr_s': (montage_snr, 'outputspec.sagittal_png'),
                                                'qc___snr_hist': (hist_, 'hist_path'),
                                                'qc___snr_val': (snr_val, 'snr_storefl')},logger)   ###
                    if not 3 in qc_montage_id_a:
                        qc_montage_id_a[3] = 'snr_a'
                        qc_montage_id_s[3] = 'snr_s'
                        qc_hist_id[3] = 'snr_hist'

                except:
                    logStandardError('QC', 'unable to get resources for SNR plot', '0051',logger)
                    raise


            #make motion parameters plot

            if 1 in c.runFunctionalPreprocessing:

                try:

                    mov_param, out_file = strat.get_node_from_resource_pool('movement_parameters',logger)
                    mov_plot = pe.Node(util.Function(input_names=['motion_parameters'],
                                                     output_names=['translation_plot',
                                                                   'rotation_plot'],
                                                     function=gen_motion_plt),
                                       name='motion_plt_%d' % num_strat)

                    workflow.connect(mov_param, out_file,
                                     mov_plot, 'motion_parameters')
                    strat.update_resource_pool({'qc___movement_trans_plot': (mov_plot, 'translation_plot'),
                                                'qc___movement_rot_plot': (mov_plot, 'rotation_plot')},logger)

                    if not 6 in qc_plot_id:
                        qc_plot_id[6] = 'movement_trans_plot'

                    if not 7 in qc_plot_id:
                        qc_plot_id[7] = 'movement_rot_plot'


                except:
                    logStandardError('QC', 'unable to get resources for Motion Parameters plot', '0052',logger)
                    raise


            # make FD plot and volumes removed
            if (1 in c.runGenerateMotionStatistics) and ('gen_motion_stats' in nodes):

                try:

                    fd, out_file = strat.get_node_from_resource_pool('frame_wise_displacement',logger)
                    excluded, out_file_ex = strat.get_node_from_resource_pool('scrubbing_frames_excluded',logger)

                    fd_plot = pe.Node(util.Function(input_names=['arr',
                                                                 'ex_vol',
                                                                 'measure'],
                                                    output_names=['hist_path'],
                                                    function=gen_plot_png),
                                      name='fd_plot_%d' % num_strat)
                    fd_plot.inputs.measure = 'FD'
                    workflow.connect(fd, out_file,
                                     fd_plot, 'arr')
                    workflow.connect(excluded, out_file_ex,
                                     fd_plot, 'ex_vol')
                    strat.update_resource_pool({'qc___fd_plot': (fd_plot, 'hist_path')},logger)
                    if not 8 in qc_plot_id:
                        qc_plot_id[8] = 'fd_plot'


                except:
                    logStandardError('QC', 'unable to get resources for FD plot', '0053',logger)
                    raise


            # make QC montages for Skull Stripping Visualization

            try:
                anat_underlay, out_file = strat.get_node_from_resource_pool('anatomical_brain',logger)
                skull, out_file_s = strat.get_node_from_resource_pool('anatomical_reorient',logger)


                montage_skull = create_montage('montage_skull_%d' % num_strat,
                                    'red', 'skull_vis')   ###

                skull_edge = pe.Node(util.Function(input_names=['file_'],
                                                   output_names=['new_fname'],
                                                   function=make_edge),
                                     name='skull_edge_%d' % num_strat)


                workflow.connect(skull, out_file_s,
                                 skull_edge, 'file_')

                workflow.connect(anat_underlay, out_file,
                                 montage_skull, 'inputspec.underlay')

                workflow.connect(skull_edge, 'new_fname',
                                 montage_skull, 'inputspec.overlay')

                strat.update_resource_pool({'qc___skullstrip_vis_a': (montage_skull, 'outputspec.axial_png'),
                                            'qc___skullstrip_vis_s': (montage_skull, 'outputspec.sagittal_png')},logger)

                if not 1 in qc_montage_id_a:
                        qc_montage_id_a[1] = 'skullstrip_vis_a'
                        qc_montage_id_s[1] = 'skullstrip_vis_s'

            except:
                logStandardError('QC', \
                'Cannot generate QC montages for Skull Stripping:'+\
                ' Resources Not Found', '0054',logger)
                raise


            ### make QC montages for mni normalized anatomical image

            try:
                mni_anat_underlay, out_file = strat.get_node_from_resource_pool('mni_normalized_anatomical',logger)

                montage_mni_anat = create_montage('montage_mni_anat_%d' % num_strat,
                                    'red', 'mni_anat')  

                workflow.connect(mni_anat_underlay, out_file,
                                 montage_mni_anat, 'inputspec.underlay')

                montage_mni_anat.inputs.inputspec.overlay = p.resource_filename('CPAC','resources/templates/MNI152_Edge_AllTissues.nii.gz')

                strat.update_resource_pool({'qc___mni_normalized_anatomical_a': (montage_mni_anat, 'outputspec.axial_png'),
                                            'qc___mni_normalized_anatomical_s': (montage_mni_anat, 'outputspec.sagittal_png')},logger)

                if not 6 in qc_montage_id_a:
                        qc_montage_id_a[6] = 'mni_normalized_anatomical_a'
                        qc_montage_id_s[6] = 'mni_normalized_anatomical_s'

            except:
                logStandardError('QC', \
                'Cannot generate QC montages for MNI '+\
                'normalized anatomical: Resources Not Found', '0054',logger)
                raise



            # make QC montages for CSF WM GM

            if 'seg_preproc' in nodes:

                try:
                    anat_underlay, out_file = strat.get_node_from_resource_pool('anatomical_brain',logger)
                    csf_overlay, out_file_csf = strat.get_node_from_resource_pool('anatomical_csf_mask',logger)
                    wm_overlay, out_file_wm = strat.get_node_from_resource_pool('anatomical_wm_mask',logger)
                    gm_overlay, out_file_gm = strat.get_node_from_resource_pool('anatomical_gm_mask',logger)

                    montage_csf_gm_wm = create_montage_gm_wm_csf('montage_csf_gm_wm_%d' % num_strat,
                                        'montage_csf_gm_wm')

                    workflow.connect(anat_underlay, out_file,
                                     montage_csf_gm_wm, 'inputspec.underlay')

                    workflow.connect(csf_overlay, out_file_csf,
                                     montage_csf_gm_wm, 'inputspec.overlay_csf')

                    workflow.connect(wm_overlay, out_file_wm,
                                     montage_csf_gm_wm, 'inputspec.overlay_wm')

                    workflow.connect(gm_overlay, out_file_gm,
                                     montage_csf_gm_wm, 'inputspec.overlay_gm')

                    strat.update_resource_pool({'qc___csf_gm_wm_a': (montage_csf_gm_wm, 'outputspec.axial_png'),
                                                'qc___csf_gm_wm_s': (montage_csf_gm_wm, 'outputspec.sagittal_png')},logger)

                    if not 2 in qc_montage_id_a:
                            qc_montage_id_a[2] = 'csf_gm_wm_a'
                            qc_montage_id_s[2] = 'csf_gm_wm_s'

                except:
                    logStandardError('QC', 'Cannot generate QC montages for'+\
                    ' WM GM CSF masks: Resources Not Found', '0055',logger)
                    raise


            # make QC montage for Mean Functional in T1 with T1 edge

            try:
                anat, out_file = strat.get_node_from_resource_pool('anatomical_brain',logger)
                m_f_a, out_file_mfa = strat.get_node_from_resource_pool('mean_functional_in_anat',logger)

                montage_anat = create_montage('montage_anat_%d' % num_strat,
                                    'red', 't1_edge_on_mean_func_in_t1')   ###

                anat_edge = pe.Node(util.Function(input_names=['file_'],
                                                   output_names=['new_fname'],
                                                   function=make_edge),
                                     name='anat_edge_%d' % num_strat)

                workflow.connect(anat, out_file,
                                 anat_edge, 'file_')


                workflow.connect(m_f_a, out_file_mfa,
                                 montage_anat, 'inputspec.underlay')

                workflow.connect(anat_edge, 'new_fname',
                                 montage_anat, 'inputspec.overlay')

                strat.update_resource_pool({'qc___mean_func_with_t1_edge_a': \
                                (montage_anat, 'outputspec.axial_png'),
                                            'qc___mean_func_with_t1_edge_s': \
                                (montage_anat, 'outputspec.sagittal_png')},logger)

                if not 4 in qc_montage_id_a:
                        qc_montage_id_a[4] = 'mean_func_with_t1_edge_a'
                        qc_montage_id_s[4] = 'mean_func_with_t1_edge_s'


            except:
                logStandardError('QC', 'Cannot generate QC montages for '+\
                'Mean Functional in T1 with T1 edge: Resources Not Found', \
                '0056',logger)
                raise

            # make QC montage for Mean Functional in MNI with MNI edge

            try:
                m_f_i, out_file = strat.get_node_from_resource_pool('mean_functional_in_mni',logger)

                montage_mfi = create_montage('montage_mfi_%d' % num_strat,
                                    'red', 'MNI_edge_on_mean_func_mni')   ###

#                  MNI_edge = pe.Node(util.Function(input_names=['file_'],
#                                                     output_names=['new_fname'],
#                                                     function=make_edge),
#                                       name='MNI_edge_%d' % num_strat)
#                  #MNI_edge.inputs.file_ = c.template_brain_only_for_func
#                 workflow.connect(MNI_edge, 'new_fname',
#                                  montage_mfi, 'inputspec.overlay')

                workflow.connect(m_f_i, out_file,
                                 montage_mfi, 'inputspec.underlay')

                montage_mfi.inputs.inputspec.overlay = \
                p.resource_filename('CPAC',\
                'resources/templates/MNI152_Edge_AllTissues.nii.gz')


                strat.update_resource_pool({'qc___mean_func_with_mni_edge_a': \
                            (montage_mfi, 'outputspec.axial_png'),
                                            'qc___mean_func_with_mni_edge_s': \
                            (montage_mfi, 'outputspec.sagittal_png')},logger)

                if not 5 in qc_montage_id_a:
                        qc_montage_id_a[5] = 'mean_func_with_mni_edge_a'
                        qc_montage_id_s[5] = 'mean_func_with_mni_edge_s'


            except:
                logStandardError('QC', \
                                 'Cannot generate QC montages for Mean Functional in'+\
                                 ' MNI with MNI edge: Resources Not Found', '0057',logger)
                raise



            '''
            # make QC montages for SCA ROI Smoothed Derivative
            if (1 in c.runSCA) and (1 in c.runROITimeseries):

                hist_sca_roi = hist.clone('hist_sca_roi_%d' % num_strat)
                hist_sca_roi.inputs.measure = 'sca_roi'

                drop_percent_sca_roi = pe.MapNode(util.Function(input_names=['measure_file',
                                                     'percent_'],
                                       output_names=['modified_measure_file'],
                                       function=drop_percent_),
                                       name='dp_sca_roi_%d' % num_strat, iterfield=['measure_file'])
                drop_percent_sca_roi.inputs.percent_ = 99.999

                if 1 in c.runZScoring:

                    hist_sca_roi_zstd = hist.clone('hist_sca_roi_zstd_%d' % num_strat)
                    hist_sca_roi_zstd.inputs.measure = 'sca_roi'

                    drop_percent_sca_roi_zstd = pe.MapNode(util.Function(input_names=['measure_file',
                                                         'percent_'],
                                           output_names=['modified_measure_file'],
                                           function=drop_percent_),
                                           name='dp_sca_roi_zstd_%d' % num_strat, iterfield=['measure_file'])
                    drop_percent_sca_roi_zstd.inputs.percent_ = 99.999

                    if c.fwhm != None:

<<<<<<< .merge_file_jcwo50
                        sca_overlay, out_file = strat.get_node_from_resource_pool('sca_roi_Z_to_standard_smooth',logger)
                        montage_sca_roi = create_montage('montage_sca_roi_standard_smooth_%d' % num_strat,
=======
                        sca_roi_smooth_zstd_overlay, out_file = strat.get_node_from_resource_pool('sca_roi_to_standard_smooth_fisher_zstd')
                        montage_sca_roi_smooth_zstd = create_montage('montage_sca_roi_standard_smooth_zstd_%d' % num_strat,
>>>>>>> .merge_file_dIlCkY
                                        'cyan_to_yellow', 'sca_roi_smooth')

                        montage_sca_roi_smooth_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func

                        workflow.connect(sca_roi_smooth_zstd_overlay, out_file,
                                         drop_percent_sca_roi_zstd, 'measure_file')

                        workflow.connect(drop_percent_sca_roi_zstd, 'modified_measure_file',
                                         montage_sca_roi_smooth_zstd, 'inputspec.overlay')

<<<<<<< .merge_file_jcwo50
                        workflow.connect(sca_overlay, out_file,
                                         hist_, 'measure_file')
                        strat.update_resource_pool({'qc___sca_roi_smooth_a': (montage_sca_roi, 'outputspec.axial_png'),
                                                'qc___sca_roi_smooth_s': (montage_sca_roi, 'outputspec.sagittal_png'),
                                                'qc___sca_roi_smooth_hist': (hist_, 'hist_path')},logger)
=======
                        workflow.connect(sca_roi_smooth_zstd_overlay, out_file,
                                         hist_sca_roi_zstd, 'measure_file')
                        strat.update_resource_pool({'qc___sca_roi_smooth_a': (montage_sca_roi_smooth_zstd, 'outputspec.axial_png'),
                                                'qc___sca_roi_smooth_s': (montage_sca_roi_smooth_zstd, 'outputspec.sagittal_png'),
                                                'qc___sca_roi_smooth_hist': (hist_sca_roi_zstd, 'hist_path')})
>>>>>>> .merge_file_dIlCkY

                        if not 9 in qc_montage_id_a:
                            qc_montage_id_a[9] = 'sca_roi_smooth_a'
                            qc_montage_id_s[9] = 'sca_roi_smooth_s'
                            qc_hist_id[9] = 'sca_roi_smooth_hist'


                    else:

<<<<<<< .merge_file_jcwo50
                        sca_overlay, out_file = strat.get_node_from_resource_pool('sca_roi_Z_to_standard',logger)
                        montage_sca_roi = create_montage('montage_sca_roi_standard_%d' % num_strat,
=======
                        sca_roi_zstd_overlay, out_file = strat.get_node_from_resource_pool('sca_roi_to_standard_fisher_zstd')
                        montage_sca_roi_zstd = create_montage('montage_sca_roi_zstd_standard_%d' % num_strat,
>>>>>>> .merge_file_dIlCkY
                                        'cyan_to_yellow', 'sca_roi')

                        montage_sca_roi_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func
                        workflow.connect(sca_roi_zstd_overlay, out_file,
                                         drop_percent_sca_roi_zstd, 'measure_file')

                        workflow.connect(drop_percent_sca_roi_zstd, 'modified_measure_file',
                                         montage_sca_roi_zstd, 'inputspec.overlay')

                        workflow.connect(sca_roi_zstd_overlay, out_file,
                                         hist_sca_roi_zstd, 'measure_file')

<<<<<<< .merge_file_jcwo50
                        strat.update_resource_pool({'qc___sca_roi_a': (montage_sca_roi, 'outputspec.axial_png'),
                                                'qc___sca_roi_s': (montage_sca_roi, 'outputspec.sagittal_png'),
                                                'qc___sca_roi_hist': (hist_, 'hist_path')},logger)
=======
                        strat.update_resource_pool({'qc___sca_roi_a': (montage_sca_roi_zstd, 'outputspec.axial_png'),
                                                'qc___sca_roi_s': (montage_sca_roi_zstd, 'outputspec.sagittal_png'),
                                                'qc___sca_roi_hist': (hist_sca_roi_zstd, 'hist_path')})
>>>>>>> .merge_file_dIlCkY

                        if not 9 in qc_montage_id_a:
                            qc_montage_id_a[9] = 'sca_roi_a'
                            qc_montage_id_s[9] = 'sca_roi_s'
                            qc_hist_id[9] = 'sca_roi_hist'



<<<<<<< .merge_file_jcwo50
                if 0 in c.runZScoring:

                    if c.fwhm != None:

                        sca_overlay, out_file = strat.get_node_from_resource_pool('sca_roi_to_standard_smooth',logger)
                        montage_sca_roi = create_montage('montage_sca_roi_standard_smooth_%d' % num_strat,
                                        'cyan_to_yellow', 'sca_roi_smooth')

                        montage_sca_roi.inputs.inputspec.underlay = c.template_brain_only_for_func
=======
                if c.fwhm != None:
>>>>>>> .merge_file_dIlCkY

                    sca_roi_smooth_overlay, out_file = strat.get_node_from_resource_pool('sca_roi_to_standard_smooth')
                    montage_sca_roi_smooth = create_montage('montage_sca_roi_standard_smooth_%d' % num_strat,
                                    'cyan_to_yellow', 'sca_roi_smooth')

                    montage_sca_roi_smooth.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(sca_roi_smooth_overlay, out_file,
                                     drop_percent_sca_roi, 'measure_file')

<<<<<<< .merge_file_jcwo50
                        workflow.connect(sca_overlay, out_file,
                                         hist_, 'measure_file')
                        strat.update_resource_pool({'qc___sca_roi_smooth_a': (montage_sca_roi, 'outputspec.axial_png'),
                                                'qc___sca_roi_smooth_s': (montage_sca_roi, 'outputspec.sagittal_png'),
                                                'qc___sca_roi_smooth_hist': (hist_, 'hist_path')},logger)
=======
                    workflow.connect(drop_percent_sca_roi, 'modified_measure_file',
                                     montage_sca_roi_smooth, 'inputspec.overlay')
>>>>>>> .merge_file_dIlCkY

                    workflow.connect(sca_roi_smooth_overlay, out_file,
                                     hist_sca_roi, 'measure_file')
                    strat.update_resource_pool({'qc___sca_roi_smooth_a': (montage_sca_roi_smooth, 'outputspec.axial_png'),
                                            'qc___sca_roi_smooth_s': (montage_sca_roi_smooth, 'outputspec.sagittal_png'),
                                            'qc___sca_roi_smooth_hist': (hist_sca_roi, 'hist_path')})

                    if not 9 in qc_montage_id_a:
                        qc_montage_id_a[9] = 'sca_roi_smooth_a'
                        qc_montage_id_s[9] = 'sca_roi_smooth_s'
                        qc_hist_id[9] = 'sca_roi_smooth_hist'


<<<<<<< .merge_file_jcwo50
                        sca_overlay, out_file = strat.get_node_from_resource_pool('sca_roi_to_standard',logger)
                        montage_sca_roi = create_montage('montage_sca_roi_standard_%d' % num_strat,
                                        'cyan_to_yellow', 'sca_roi')
=======
                else:
>>>>>>> .merge_file_dIlCkY

                    sca_roi_overlay, out_file = strat.get_node_from_resource_pool('sca_roi_to_standard')
                    montage_sca_roi = create_montage('montage_sca_roi_standard_%d' % num_strat,
                                    'cyan_to_yellow', 'sca_roi')

                    montage_sca_roi.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(sca_roi_overlay, out_file,
                                     drop_percent_sca_roi, 'measure_file')

                    workflow.connect(drop_percent_sca_roi, 'modified_measure_file',
                                     montage_sca_roi, 'inputspec.overlay')

<<<<<<< .merge_file_jcwo50
                        strat.update_resource_pool({'qc___sca_roi_a': (montage_sca_roi, 'outputspec.axial_png'),
                                                'qc___sca_roi_s': (montage_sca_roi, 'outputspec.sagittal_png'),
                                                'qc___sca_roi_hist': (hist_, 'hist_path')},logger)
=======
                    workflow.connect(sca_roi_overlay, out_file,
                                     hist_sca_roi, 'measure_file')
>>>>>>> .merge_file_dIlCkY

                    strat.update_resource_pool({'qc___sca_roi_a': (montage_sca_roi, 'outputspec.axial_png'),
                                            'qc___sca_roi_s': (montage_sca_roi, 'outputspec.sagittal_png'),
                                            'qc___sca_roi_hist': (hist_sca_roi, 'hist_path')})

                    if not 9 in qc_montage_id_a:
                        qc_montage_id_a[9] = 'sca_roi_a'
                        qc_montage_id_s[9] = 'sca_roi_s'
                        qc_hist_id[9] = 'sca_roi_hist'




            
            # make QC montages for SCA Smoothed Derivative
            if (1 in c.runSCA) and (1 in c.runVoxelTimeseries):

                hist_sca_seed = hist.clone('hist_sca_seeds_%d' % num_strat)
                hist_sca_seed.inputs.measure = 'sca_seeds'

                drop_percent_sca_seed = pe.MapNode(util.Function(input_names=['measure_file',
                                                     'percent_'],
                                       output_names=['modified_measure_file'],
                                       function=drop_percent_),
                                       name='dp_sca_seed_%d' % num_strat, iterfield=['measure_file'])
                drop_percent_sca_seed.inputs.percent_ = 99.999


                if 1 in c.runZScoring:

                    hist_sca_seed_zstd = hist.clone('hist_sca_seeds_zstd_%d' % num_strat)
                    hist_sca_seed_zstd.inputs.measure = 'sca_seeds'

                    drop_percent_sca_seed_zstd = pe.MapNode(util.Function(input_names=['measure_file',
                                                         'percent_'],
                                           output_names=['modified_measure_file'],
                                           function=drop_percent_),
                                           name='dp_sca_seed_zstd_%d' % num_strat, iterfield=['measure_file'])
                    drop_percent_sca_seed_zstd.inputs.percent_ = 99.999

                    if c.fwhm != None:

<<<<<<< .merge_file_jcwo50
                        sca_overlay, out_file = strat.get_node_from_resource_pool('sca_seed_Z_to_standard_smooth',logger)
                        montage_sca_seeds = create_montage('montage_seed_standard_smooth_%d' % num_strat,
=======
                        sca_seed_smooth_zstd_overlay, out_file = strat.get_node_from_resource_pool('sca_seed_to_standard_smooth_fisher_zstd')
                        montage_sca_seeds_smooth_zstd = create_montage('montage_seed_standard_smooth_zstd_%d' % num_strat,
>>>>>>> .merge_file_dIlCkY
                                        'cyan_to_yellow', 'sca_seed_smooth')

                        montage_sca_seeds_smooth_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func
                        workflow.connect(sca_seed_smooth_zstd_overlay, out_file,
                                         drop_percent_sca_seed_zstd, 'measure_file')

                        workflow.connect(drop_percent_sca_seed_zstd, 'modified_measure_file',
                                         montage_sca_seeds_smooth_zstd, 'inputspec.overlay')

                        workflow.connect(sca_seed_smooth_zstd_overlay, out_file,
                                         hist_sca_seed_zstd, 'measure_file')

<<<<<<< .merge_file_jcwo50
                        strat.update_resource_pool({'qc___sca_seeds_smooth_a': (montage_sca_seeds, 'outputspec.axial_png'),
                                                'qc___sca_seeds_smooth_s': (montage_sca_seeds, 'outputspec.sagittal_png'),
                                                'qc___sca_seeds_smooth_hist': (hist_, 'hist_path')},logger)
=======
                        strat.update_resource_pool({'qc___sca_seeds_smooth_a': (montage_sca_seeds_smooth_zstd, 'outputspec.axial_png'),
                                                'qc___sca_seeds_smooth_s': (montage_sca_seeds_smooth_zstd, 'outputspec.sagittal_png'),
                                                'qc___sca_seeds_smooth_hist': (hist_sca_seed_zstd, 'hist_path')})
>>>>>>> .merge_file_dIlCkY

                        if not 10 in qc_montage_id_a:
                            qc_montage_id_a[10] = 'sca_seeds_smooth_a'
                            qc_montage_id_s[10] = 'sca_seeds_smooth_s'
                            qc_hist_id[10] = 'sca_seeds_smooth_hist'

                    else:
                
<<<<<<< .merge_file_jcwo50
                        sca_overlay, out_file = strat.get_node_from_resource_pool('sca_seed_Z_to_standard',logger)
                        montage_sca_seeds = create_montage('montage_sca_seed_standard_%d' % num_strat,
=======
                        sca_seed_zstd_overlay, out_file = strat.get_node_from_resource_pool('sca_seed_to_standard_fisher_zstd')
                        montage_sca_seeds_zstd = create_montage('montage_sca_seed_standard_zstd_%d' % num_strat,
>>>>>>> .merge_file_dIlCkY
                                        'cyan_to_yellow', 'sca_seed')

                        montage_sca_seeds_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func
                        workflow.connect(sca_seed_zstd_overlay, out_file,
                                         drop_percent_sca_seed_zstd, 'measure_file')

                        workflow.connect(drop_percent_sca_seed_zstd, 'modified_measure_file',
                                         montage_sca_seeds_zstd, 'inputspec.overlay')

<<<<<<< .merge_file_jcwo50
                        workflow.connect(sca_overlay, out_file,
                                         hist_, 'measure_file')
                        strat.update_resource_pool({'qc___sca_seeds_a': (montage_sca_seeds, 'outputspec.axial_png'),
                                                'qc___sca_seeds_s': (montage_sca_seeds, 'outputspec.sagittal_png'),
                                                'qc___sca_seeds_hist': (hist_, 'hist_path')},logger)
=======
                        workflow.connect(sca_seed_zstd_overlay, out_file,
                                         hist_sca_seed_zstd, 'measure_file')
                        strat.update_resource_pool({'qc___sca_seeds_a': (montage_sca_seeds_zstd, 'outputspec.axial_png'),
                                                'qc___sca_seeds_s': (montage_sca_seeds_zstd, 'outputspec.sagittal_png'),
                                                'qc___sca_seeds_hist': (hist_sca_seed_zstd, 'hist_path')})
>>>>>>> .merge_file_dIlCkY

                        if not 10 in qc_montage_id_a:
                            qc_montage_id_a[10] = 'sca_seeds_a'
                            qc_montage_id_s[10] = 'sca_seeds_s'
                            qc_hist_id[10] = 'sca_seeds_hist'



                if c.fwhm != None:

                    sca_seed_smooth_overlay, out_file = strat.get_node_from_resource_pool('sca_seed_to_standard_smooth')
                    montage_sca_seeds_smooth = create_montage('montage_seed_standard_smooth_%d' % num_strat,
                                    'cyan_to_yellow', 'sca_seed_smooth')

<<<<<<< .merge_file_jcwo50
                        sca_overlay, out_file = strat.get_node_from_resource_pool('sca_seed_to_standard_smooth',logger)
                        montage_sca_seeds = create_montage('montage_seed_standard_smooth_%d' % num_strat,
                                        'cyan_to_yellow', 'sca_seed_smooth')
=======
                    montage_sca_seeds_smooth.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(sca_seed_smooth_overlay, out_file,
                                     drop_percent_sca_seed, 'measure_file')
>>>>>>> .merge_file_dIlCkY

                    workflow.connect(drop_percent_sca_seed, 'modified_measure_file',
                                     montage_sca_seeds_smooth, 'inputspec.overlay')

                    workflow.connect(sca_seed_smooth_overlay, out_file,
                                     hist_sca_seed, 'measure_file')

                    strat.update_resource_pool({'qc___sca_seeds_smooth_a': (montage_sca_seeds_smooth, 'outputspec.axial_png'),
                                            'qc___sca_seeds_smooth_s': (montage_sca_seeds_smooth, 'outputspec.sagittal_png'),
                                            'qc___sca_seeds_smooth_hist': (hist_sca_seed, 'hist_path')})

<<<<<<< .merge_file_jcwo50
                        strat.update_resource_pool({'qc___sca_seeds_smooth_a': (montage_sca_seeds, 'outputspec.axial_png'),
                                                'qc___sca_seeds_smooth_s': (montage_sca_seeds, 'outputspec.sagittal_png'),
                                                'qc___sca_seeds_smooth_hist': (hist_, 'hist_path')},logger)
=======
                    if not 10 in qc_montage_id_a:
                        qc_montage_id_a[10] = 'sca_seeds_smooth_a'
                        qc_montage_id_s[10] = 'sca_seeds_smooth_s'
                        qc_hist_id[10] = 'sca_seeds_smooth_hist'
>>>>>>> .merge_file_dIlCkY


                else:
                
<<<<<<< .merge_file_jcwo50
                        sca_overlay, out_file = strat.get_node_from_resource_pool('sca_seed_to_standard',logger)
                        montage_sca_seeds = create_montage('montage_sca_seed_standard_%d' % num_strat,
                                        'cyan_to_yellow', 'sca_seed')
=======
                    sca_seed_overlay, out_file = strat.get_node_from_resource_pool('sca_seed_to_standard')
                    montage_sca_seeds = create_montage('montage_sca_seed_standard_%d' % num_strat,
                                    'cyan_to_yellow', 'sca_seed')
>>>>>>> .merge_file_dIlCkY

                    montage_sca_seeds.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(sca_seed_overlay, out_file,
                                     drop_percent_sca_seed, 'measure_file')

                    workflow.connect(drop_percent_sca_seed, 'modified_measure_file',
                                     montage_sca_seeds, 'inputspec.overlay')

<<<<<<< .merge_file_jcwo50
                        workflow.connect(sca_overlay, out_file,
                                         hist_, 'measure_file')
                        strat.update_resource_pool({'qc___sca_seeds_a': (montage_sca_seeds, 'outputspec.axial_png'),
                                                'qc___sca_seeds_s': (montage_sca_seeds, 'outputspec.sagittal_png'),
                                                'qc___sca_seeds_hist': (hist_, 'hist_path')},logger)

                        if not 10 in qc_montage_id_a:
                            qc_montage_id_a[10] = 'sca_seeds_a'
                            qc_montage_id_s[10] = 'sca_seeds_s'
                            qc_hist_id[10] = 'sca_seeds_hist'
=======
                    workflow.connect(sca_seed_overlay, out_file,
                                     hist_sca_seed, 'measure_file')
                    strat.update_resource_pool({'qc___sca_seeds_a': (montage_sca_seeds, 'outputspec.axial_png'),
                                            'qc___sca_seeds_s': (montage_sca_seeds, 'outputspec.sagittal_png'),
                                            'qc___sca_seeds_hist': (hist_sca_seed, 'hist_path')})
>>>>>>> .merge_file_dIlCkY

                    if not 10 in qc_montage_id_a:
                        qc_montage_id_a[10] = 'sca_seeds_a'
                        qc_montage_id_s[10] = 'sca_seeds_s'
                        qc_hist_id[10] = 'sca_seeds_hist'

            '''


            # make QC montages for Network Centrality
            if 1 in c.runNetworkCentrality:

                hist_ = hist.clone('hist_centrality_%d' % num_strat)
                hist_.inputs.measure = 'centrality'

                drop_percent = pe.MapNode(util.Function(input_names=['measure_file',
                                                     'percent_'],
                                       output_names=['modified_measure_file'],
                                       function=drop_percent_),
                                       name='dp_centrality_%d' % num_strat, iterfield=['measure_file'])
                drop_percent.inputs.percent_ = 99.999
                if c.fwhm != None:

                    centrality_overlay, out_file = strat.get_node_from_resource_pool('centrality_outputs_smoothed',logger)
                    montage_centrality = create_montage('montage_centrality_%d' % num_strat,
                                    'cyan_to_yellow', 'centrality')

                    montage_centrality.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(centrality_overlay, out_file,
                                     drop_percent, 'measure_file')

                    workflow.connect(drop_percent, 'modified_measure_file',
                                     montage_centrality, 'inputspec.overlay')

                    workflow.connect(centrality_overlay, out_file,
                                     hist_, 'measure_file')
                    strat.update_resource_pool({'qc___centrality_smooth_a': (montage_centrality, 'outputspec.axial_png'),
                                            'qc___centrality_smooth_s': (montage_centrality, 'outputspec.sagittal_png'),
                                            'qc___centrality_smooth_hist': (hist_, 'hist_path')},logger)
                    if not 11 in qc_montage_id_a:
                        qc_montage_id_a[11] = 'centrality_smooth_a'
                        qc_montage_id_s[11] = 'centrality_smooth_s'
                        qc_hist_id[11] = 'centrality_smooth_hist'



                else:

                    centrality_overlay, out_file = strat.get_node_from_resource_pool('centrality_outputs',logger)
                    montage_centrality = create_montage('montage_centrality_standard_%d' % num_strat,
                                    'cyan_to_yellow', 'centrality')

                    montage_centrality.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(centrality_overlay, out_file,
                                     drop_percent, 'measure_file')

                    workflow.connect(drop_percent, 'modified_measure_file',
                                     montage_centrality, 'inputspec.overlay')

                    workflow.connect(centrality_overlay, out_file,
                                     hist_, 'measure_file')
                    strat.update_resource_pool({'qc___centrality_a': (montage_centrality, 'outputspec.axial_png'),
                                            'qc___centrality_s': (montage_centrality, 'outputspec.sagittal_png'),
                                            'qc___centrality_hist': (hist_, 'hist_path')},logger)
                    if not 11 in qc_montage_id_a:
                        qc_montage_id_a[11] = 'centrality_a'
                        qc_montage_id_s[11] = 'centrality_s'
                        qc_hist_id[11] = 'centrality_hist'





            #QC Montages for MultiReg SCA
            if (1 in c.runMultRegSCA) and (1 in c.runROITimeseries):


                hist_ = hist.clone('hist_dr_sca_%d' % num_strat)
                hist_.inputs.measure = 'temporal_regression_sca'

                drop_percent = pe.MapNode(util.Function(input_names=['measure_file',
                                                      'percent_'],
                                       output_names=['modified_measure_file'],
                                       function=drop_percent_),
                                       name='dp_temporal_regression_sca_%d' % num_strat, iterfield=['measure_file'])
                drop_percent.inputs.percent_ = 99.98

                if c.fwhm != None:


                    temporal_regression_sca_overlay, out_file = strat.get_node_from_resource_pool('sca_tempreg_maps_zstat_files_smooth',logger)
                    montage_temporal_regression_sca = create_montage('montage_temporal_regression_sca_%d' % num_strat,
                                      'cyan_to_yellow', 'temporal_regression_sca_smooth')

                    montage_temporal_regression_sca.inputs.inputspec.underlay = c.template_brain_only_for_func
                    strat.update_resource_pool({'qc___temporal_regression_sca_smooth_a': (montage_temporal_regression_sca, 'outputspec.axial_png'),
                                            'qc___temporal_regression_sca_smooth_s': (montage_temporal_regression_sca, 'outputspec.sagittal_png'),
                                            'qc___temporal_regression_sca_smooth_hist': (hist_, 'hist_path')},logger)

                    if not 12 in qc_montage_id_a:
                        qc_montage_id_a[12] = 'temporal_regression_sca_smooth_a'
                        qc_montage_id_s[12] = 'temporal_regression_sca_smooth_s'
                        qc_hist_id[12] = 'temporal_regression_sca_smooth_hist'

                else:

                    temporal_regression_sca_overlay, out_file = strat.get_node_from_resource_pool('sca_tempreg_maps_zstat_files',logger)
                    montage_temporal_regression_sca = create_montage('montage_temporal_regression_sca_%d' % num_strat,
                                      'cyan_to_yellow', 'temporal_regression_sca')

                    montage_temporal_regression_sca.inputs.inputspec.underlay = c.template_brain_only_for_func
                    strat.update_resource_pool({'qc___temporal_regression_sca_a': (montage_temporal_regression_sca, 'outputspec.axial_png'),
                                            'qc___temporal_regression_sca_s': (montage_temporal_regression_sca, 'outputspec.sagittal_png'),
                                            'qc___temporal_regression_sca_hist': (hist_, 'hist_path')},logger)

                    if not 12 in qc_montage_id_a:
                        qc_montage_id_a[12] = 'temporal_regression_sca_a'
                        qc_montage_id_s[12] = 'temporal_regression_sca_s'
                        qc_hist_id[12] = 'temporal_regression_sca_hist'




                workflow.connect(temporal_regression_sca_overlay, out_file,
                                 drop_percent, 'measure_file')

                workflow.connect(drop_percent, 'modified_measure_file',
                                 montage_temporal_regression_sca, 'inputspec.overlay')
                workflow.connect(temporal_regression_sca_overlay, out_file,
                                     hist_, 'measure_file')

            #QC Montages for MultiReg DR
            if (1 in c.runDualReg) and (1 in c.runSpatialRegression):


                hist_ = hist.clone('hist_temp_dr_%d' % num_strat)
                hist_.inputs.measure = 'temporal_dual_regression'

                drop_percent = pe.MapNode(util.Function(input_names=['measure_file',
                                                      'percent_'],
                                       output_names=['modified_measure_file'],
                                       function=drop_percent_),
                                       name='dp_temporal_dual_regression_%d' % \
                                    num_strat, iterfield=['measure_file'])
                drop_percent.inputs.percent_ = 99.98

                if c.fwhm != None:

                    temporal_dual_regression_overlay, out_file = strat.get_node_from_resource_pool('dr_tempreg_maps_zstat_files_smooth',logger)
                    montage_temporal_dual_regression = create_montage('montage_temporal_dual_regression_%d' % num_strat,
                                      'cyan_to_yellow', 'temporal_dual_regression_smooth')

                    montage_temporal_dual_regression.inputs.inputspec.underlay = c.template_brain_only_for_func
                    strat.update_resource_pool({'qc___temporal_dual_regression_smooth_a': (montage_temporal_dual_regression, 'outputspec.axial_png'),
                                            'qc___temporal_dual_regression_smooth_s': (montage_temporal_dual_regression, 'outputspec.sagittal_png'),
                                            'qc___temporal_dual_regression_smooth_hist': (hist_, 'hist_path')},logger)
                    if not 13 in qc_montage_id_a:
                        qc_montage_id_a[13] = 'temporal_dual_regression_smooth_a'
                        qc_montage_id_s[13] = 'temporal_dual_regression_smooth_s'
                        qc_hist_id[13] = 'temporal_dual_regression_smooth_hist'


                else:

                    temporal_dual_regression_overlay, out_file = strat.get_node_from_resource_pool('dr_tempreg_maps_zstat_files',logger)
                    montage_temporal_dual_regression = create_montage('montage_temporal_dual_regression_%d' % num_strat,

                                      'cyan_to_yellow', 'temporal_dual_regression')

                    montage_temporal_dual_regression.inputs.inputspec.underlay = c.template_brain_only_for_func
                    strat.update_resource_pool({'qc___temporal_dual_regression_a': (montage_temporal_dual_regression, 'outputspec.axial_png'),
                                            'qc___temporal_dual_regression_s': (montage_temporal_dual_regression, 'outputspec.sagittal_png'),
                                            'qc___temporal_dual_regression_hist': (hist_, 'hist_path')},logger)
                    if not 13 in qc_montage_id_a:
                        qc_montage_id_a[13] = 'temporal_dual_regression_a'
                        qc_montage_id_s[13] = 'temporal_dual_regression_s'
                        qc_hist_id[13] = 'temporal_dual_regression_hist'

                workflow.connect(temporal_dual_regression_overlay, out_file,
                                 drop_percent, 'measure_file')

                workflow.connect(drop_percent, 'modified_measure_file',
                                 montage_temporal_dual_regression, 'inputspec.overlay')
                workflow.connect(temporal_dual_regression_overlay, out_file,
                                     hist_, 'measure_file')



            if 1 in c.runVMHC:
                hist_ = hist.clone('hist_vmhc_%d' % num_strat)
                hist_.inputs.measure = 'vmhc'

                drop_percent = pe.Node(util.Function(input_names=['measure_file',
                                                     'percent_'],
                                       output_names=['modified_measure_file'],
                                       function=drop_percent_),
                                       name='dp_vmhc%d' % num_strat)
                drop_percent.inputs.percent_ = 99.98

                vmhc_overlay, out_file = strat.get_node_from_resource_pool('vmhc_fisher_zstd_zstat_map',logger)

                montage_vmhc = create_montage('montage_vmhc_%d' % num_strat,
                                  'cyan_to_yellow', 'vmhc_smooth')

                montage_vmhc.inputs.inputspec.underlay = c.template_brain_only_for_func
                workflow.connect(vmhc_overlay, out_file,
                                 drop_percent, 'measure_file')

                workflow.connect(drop_percent, 'modified_measure_file',
                                 montage_vmhc, 'inputspec.overlay')
                workflow.connect(vmhc_overlay, out_file,
                                     hist_, 'measure_file')
                strat.update_resource_pool({'qc___vmhc_smooth_a': (montage_vmhc, 'outputspec.axial_png'),
                                            'qc___vmhc_smooth_s': (montage_vmhc, 'outputspec.sagittal_png'),
                                            'qc___vmhc_smooth_hist': (hist_, 'hist_path')},logger)

                if not 14 in qc_montage_id_a:
                    qc_montage_id_a[14] = 'vmhc_smooth_a'
                    qc_montage_id_s[14] = 'vmhc_smooth_s'
                    qc_hist_id[14] = 'vmhc_smooth_hist'




            if 1 in c.runReHo:
                hist_ = hist.clone('hist_reho_%d' % num_strat)
                hist_.inputs.measure = 'reho'

                drop_percent = pe.Node(util.Function(input_names=['measure_file',
                                                     'percent_'],
                                       output_names=['modified_measure_file'],
                                       function=drop_percent_),
                                       name='dp_reho_%d' % num_strat)
                drop_percent.inputs.percent_ = 99.999

                if 1 in c.runZScoring:

                    hist_reho_zstd = hist.clone('hist_reho_zstd_%d' % num_strat)
                    hist_reho_zstd.inputs.measure = 'reho_zstd'

                    drop_percent_zstd = pe.Node(util.Function(input_names=['measure_file',
                                                         'percent_'],
                                           output_names=['modified_measure_file'],
                                           function=drop_percent_),
                                           name='dp_reho_zstd_%d' % num_strat)
                    drop_percent_zstd.inputs.percent_ = 99.999

                    if c.fwhm != None:

                        reho_zstd_overlay, out_file = strat.get_node_from_resource_pool('reho_to_standard_smooth_zstd',logger)
                        montage_reho_zstd = create_montage('montage_reho_zstd_%d' % num_strat,
                                      'cyan_to_yellow', 'reho_standard_smooth_zstd')
                        montage_reho_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func
                        workflow.connect(reho_zstd_overlay, out_file,
                                         hist_reho_zstd, 'measure_file')
                        strat.update_resource_pool({'qc___reho_zstd_smooth_a': (montage_reho_zstd, 'outputspec.axial_png'),
                                                'qc___reho_zstd_smooth_s': (montage_reho_zstd, 'outputspec.sagittal_png'),
                                                'qc___reho_zstd_smooth_hist': (hist_reho_zstd, 'hist_path')},logger)


                        if not 15 in qc_montage_id_a:
                            qc_montage_id_a[15] = 'reho_zstd_smooth_a'
                            qc_montage_id_s[15] = 'reho_zstd_smooth_s'
                            qc_hist_id[15] = 'reho_zstd_smooth_hist'


                    else:

                        reho_zstd_overlay, out_file = strat.get_node_from_resource_pool('reho_to_standard_zstd',logger)
                        montage_reho_zstd = create_montage('montage_reho_zstd_%d' % num_strat,
                                      'cyan_to_yellow', 'reho_standard_zstd')
                        montage_reho_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func
                        workflow.connect(reho_zstd_overlay, out_file,
                                         hist_reho_zstd, 'measure_file')
                        strat.update_resource_pool({'qc___reho_zstd_a': (montage_reho_zstd, 'outputspec.axial_png'),
                                                'qc___reho_zstd_s': (montage_reho_zstd, 'outputspec.sagittal_png'),
                                                'qc___reho_zstd_hist': (hist_reho_zstd, 'hist_path')},logger)


                        if not 15 in qc_montage_id_a:
                            qc_montage_id_a[15] = 'reho_zstd_a'
                            qc_montage_id_s[15] = 'reho_zstd_s'
                            qc_hist_id[15] = 'reho_zstd_hist'


                    workflow.connect(reho_zstd_overlay, out_file,
                                     drop_percent_zstd, 'measure_file')


                    workflow.connect(drop_percent_zstd, 'modified_measure_file',
                                     montage_reho_zstd, 'inputspec.overlay')


                

                if c.fwhm != None:
                    reho_overlay, out_file = strat.get_node_from_resource_pool('reho_to_standard_smooth',logger)
                    montage_reho = create_montage('montage_reho_%d' % num_strat,
                                  'cyan_to_yellow', 'reho_standard_smooth')
                    montage_reho.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(reho_overlay, out_file,
                                     hist_, 'measure_file')
                    strat.update_resource_pool({'qc___reho_smooth_a': (montage_reho, 'outputspec.axial_png'),
                                                'qc___reho_smooth_s': (montage_reho, 'outputspec.sagittal_png'),
                                                'qc___reho_smooth_hist': (hist_, 'hist_path')},logger)

                    if not 15 in qc_montage_id_a:
                        qc_montage_id_a[15] = 'reho_smooth_a'
                        qc_montage_id_s[15] = 'reho_smooth_s'
                        qc_hist_id[15] = 'reho_smooth_hist'

                else:
                    reho_overlay, out_file = strat.get_node_from_resource_pool('reho_to_standard',logger)
                    montage_reho = create_montage('montage_reho_%d' % num_strat,
                                  'cyan_to_yellow', 'reho_standard')
                    montage_reho.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(reho_overlay, out_file,
                                     hist_, 'measure_file')
                    strat.update_resource_pool({'qc___reho_a': (montage_reho, 'outputspec.axial_png'),

                                                'qc___reho_s': (montage_reho, 'outputspec.sagittal_png'),
                                                'qc___reho_hist': (hist_, 'hist_path')},logger)

                    if not 15 in qc_montage_id_a:
                        qc_montage_id_a[15] = 'reho_a'
                        qc_montage_id_s[15] = 'reho_s'
                        qc_hist_id[15] = 'reho_hist'


                workflow.connect(reho_overlay, out_file,
                                 drop_percent, 'measure_file')

                workflow.connect(drop_percent, 'modified_measure_file',
                                 montage_reho, 'inputspec.overlay')



            if 1 in c.runALFF:
                hist_alff = hist.clone('hist_alff_%d' % num_strat)
                hist_alff.inputs.measure = 'alff'

                hist_falff = hist.clone('hist_falff_%d' % num_strat)
                hist_falff.inputs.measure = 'falff'


                drop_percent = pe.Node(util.Function(input_names=['measure_file',
                                                     'percent_'],
                                       output_names=['modified_measure_file'],
                                       function=drop_percent_),
                                       name='dp_alff_%d' % num_strat)
                drop_percent.inputs.percent_ = 99.7

                drop_percent_falff = drop_percent.clone('dp_falff_%d' % num_strat)
                drop_percent_falff.inputs.percent_ = 99.999

                if 1 in c.runZScoring:

                    hist_alff_zstd = hist.clone('hist_alff_zstd_%d' % num_strat)
                    hist_alff_zstd.inputs.measure = 'alff_zstd'

                    hist_falff_zstd = hist.clone('hist_falff_zstd_%d' % num_strat)
                    hist_falff_zstd.inputs.measure = 'falff_zstd'


                    drop_percent_zstd = pe.Node(util.Function(input_names=['measure_file',
                                                         'percent_'],
                                           output_names=['modified_measure_file'],
                                           function=drop_percent_),
                                           name='dp_alff_zstd_%d' % num_strat)
                    drop_percent_zstd.inputs.percent_ = 99.7

                    drop_percent_falff_zstd = drop_percent.clone('dp_falff_zstd_%d' % num_strat)
                    drop_percent_falff_zstd.inputs.percent_ = 99.999


                    if c.fwhm != None:

                        alff_zstd_overlay, out_file = strat.get_node_from_resource_pool('alff_to_standard_smooth_zstd',logger)
                        falff_zstd_overlay, out_file_f = strat.get_node_from_resource_pool('falff_to_standard_smooth_zstd',logger)
                        montage_alff_zstd = create_montage('montage_alff_zstd_%d' % num_strat,
                                      'cyan_to_yellow', 'alff_standard_smooth_zstd')
                        montage_alff_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func
                        montage_falff_zstd = create_montage('montage_falff_zstd_%d' % num_strat,
                                      'cyan_to_yellow', 'falff_standard_smooth_zstd')
                        montage_falff_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func
                        workflow.connect(alff_zstd_overlay, out_file,
                                         hist_alff_zstd, 'measure_file')

                        workflow.connect(falff_zstd_overlay, out_file_f,
                                         hist_falff_zstd, 'measure_file')
                        strat.update_resource_pool({'qc___alff_smooth_a': (montage_alff_zstd, 'outputspec.axial_png'),
                                                'qc___alff_smooth_s': (montage_alff_zstd, 'outputspec.sagittal_png'),
                                                'qc___falff_smooth_a': (montage_falff_zstd, 'outputspec.axial_png'),
                                                'qc___falff_smooth_s': (montage_falff_zstd, 'outputspec.sagittal_png'),
                                                'qc___alff_smooth_hist': (hist_alff_zstd, 'hist_path'),
                                                'qc___falff_smooth_hist': (hist_falff_zstd, 'hist_path')},logger)

                        if not 16 in qc_montage_id_a:
                            qc_montage_id_a[16] = 'alff_smooth_a'
                            qc_montage_id_s[16] = 'alff_smooth_s'
                            qc_hist_id[16] = 'alff_smooth_hist'

                        if not 17 in qc_montage_id_a:
                            qc_montage_id_a[17] = 'falff_smooth_a'
                            qc_montage_id_s[17] = 'falff_smooth_s'
                            qc_hist_id[17] = 'falff_smooth_hist'



                    else:
                        alff_zstd_overlay, out_file = strat.get_node_from_resource_pool('alff_to_standard_zstd',logger)
                        falff_zstd_overlay, out_file = strat.get_node_from_resource_pool('falff_to_standard_zstd',logger)
                        montage_alff_zstd = create_montage('montage_alff_zstd_%d' % num_strat,
                                      'cyan_to_yellow', 'alff_standard_zstd')
                        montage_alff_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func
                        montage_falff_zstd = create_montage('montage_falff_zstd_%d' % num_strat,
                                      'cyan_to_yellow', 'falff_standard_zstd')
                        montage_falff_zstd.inputs.inputspec.underlay = c.template_brain_only_for_func
                        workflow.connect(alff_zstd_overlay, out_file,
                                         hist_alff_zstd, 'measure_file')

                        workflow.connect(falff_zstd_overlay, out_file_f,
                                         hist_falff_zstd, 'measure_file')
                        strat.update_resource_pool({'qc___alff_zstd_a': (montage_alff_zstd, 'outputspec.axial_png'),
                                                'qc___alff_zstd_s': (montage_alff_zstd, 'outputspec.sagittal_png'),
                                                'qc___falff_zstd_a': (montage_falff_zstd, 'outputspec.axial_png'),
                                                'qc___falff_zstd_s': (montage_falff_zstd, 'outputspec.sagittal_png'),
                                                'qc___alff_zstd_hist': (hist_alff_zstd, 'hist_path'),
                                                'qc___falff_zstd_hist': (hist_falff_zstd, 'hist_path')},logger)


                        if not 16 in qc_montage_id_a:
                            qc_montage_id_a[16] = 'alff_a'
                            qc_montage_id_s[16] = 'alff_smooth_s'
                            qc_hist_id[16] = 'alff_smooth_hist'

                        if not 16 in qc_montage_id_a:
                            qc_montage_id_a[17] = 'falff_a'
                            qc_montage_id_s[17] = 'falff_s'
                            qc_hist_id[17] = 'falff_hist'


                    workflow.connect(alff_zstd_overlay, out_file,
                                     drop_percent_zstd, 'measure_file')

                    workflow.connect(drop_percent_zstd, 'modified_measure_file',
                                     montage_alff_zstd, 'inputspec.overlay')
                    workflow.connect(falff_zstd_overlay, out_file,
                                     drop_percent_falff_zstd, 'measure_file')
                    workflow.connect(drop_percent_falff_zstd, 'modified_measure_file',
                                     montage_falff_zstd, 'inputspec.overlay')





                if c.fwhm != None:
                    alff_overlay, out_file = strat.get_node_from_resource_pool('alff_to_standard_smooth',logger)
                    falff_overlay, out_file_f = strat.get_node_from_resource_pool('falff_to_standard_smooth',logger)
                    montage_alff = create_montage('montage_alff_%d' % num_strat,
                                  'cyan_to_yellow', 'alff_standard_smooth')
                    montage_alff.inputs.inputspec.underlay = c.template_brain_only_for_func
                    montage_falff = create_montage('montage_falff_%d' % num_strat,
                                  'cyan_to_yellow', 'falff_standard_smooth')
                    montage_falff.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(alff_overlay, out_file,
                                     hist_alff, 'measure_file')

                    workflow.connect(falff_overlay, out_file_f,
                                     hist_falff, 'measure_file')
                    strat.update_resource_pool({'qc___alff_smooth_a': (montage_alff, 'outputspec.axial_png'),
                                            'qc___alff_smooth_s': (montage_alff, 'outputspec.sagittal_png'),
                                            'qc___falff_smooth_a': (montage_falff, 'outputspec.axial_png'),
                                            'qc___falff_smooth_s': (montage_falff, 'outputspec.sagittal_png'),
                                            'qc___alff_smooth_hist': (hist_alff, 'hist_path'),
                                            'qc___falff_smooth_hist': (hist_falff, 'hist_path')},logger)

                    if not 16 in qc_montage_id_a:
                        qc_montage_id_a[16] = 'alff_smooth_a'
                        qc_montage_id_s[16] = 'alff_smooth_s'
                        qc_hist_id[16] = 'alff_smooth_hist'

                    if not 17 in qc_montage_id_a:
                        qc_montage_id_a[17] = 'falff_smooth_a'
                        qc_montage_id_s[17] = 'falff_smooth_s'
                        qc_hist_id[17] = 'falff_smooth_hist'


                else:
                    alff_overlay, out_file = strat.get_node_from_resource_pool('alff_to_standard',logger)
                    falff_overlay, out_file = strat.get_node_from_resource_pool('falff_to_standard',logger)
                    montage_alff = create_montage('montage_alff_%d' % num_strat,
                                  'cyan_to_yellow', 'alff_standard')
                    montage_alff.inputs.inputspec.underlay = c.template_brain_only_for_func
                    montage_falff = create_montage('montage_falff_%d' % num_strat,
                                  'cyan_to_yellow', 'falff_standard')
                    montage_falff.inputs.inputspec.underlay = c.template_brain_only_for_func
                    workflow.connect(alff_overlay, out_file,
                                     hist_alff, 'measure_file')

                    workflow.connect(falff_overlay, out_file_f,
                                     hist_falff, 'measure_file')
                    strat.update_resource_pool({'qc___alff_a': (montage_alff, 'outputspec.axial_png'),
                                            'qc___alff_s': (montage_alff, 'outputspec.sagittal_png'),
                                            'qc___falff_a': (montage_falff, 'outputspec.axial_png'),
                                            'qc___falff_s': (montage_falff, 'outputspec.sagittal_png'),
                                            'qc___alff_hist': (hist_alff, 'hist_path'),
                                            'qc___falff_hist': (hist_falff, 'hist_path')},logger)

                    if not 16 in qc_montage_id_a:
                        qc_montage_id_a[16] = 'alff_a'
                        qc_montage_id_s[16] = 'alff_smooth_s'
                        qc_hist_id[16] = 'alff_smooth_hist'

                    if not 16 in qc_montage_id_a:
                        qc_montage_id_a[17] = 'falff_a'
                        qc_montage_id_s[17] = 'falff_s'
                        qc_hist_id[17] = 'falff_hist'



                workflow.connect(alff_overlay, out_file,
                                 drop_percent, 'measure_file')

                workflow.connect(drop_percent, 'modified_measure_file',
                                 montage_alff, 'inputspec.overlay')

                workflow.connect(falff_overlay, out_file,
                                 drop_percent_falff, 'measure_file')

                workflow.connect(drop_percent_falff, 'modified_measure_file',
                                 montage_falff, 'inputspec.overlay')




            num_strat += 1
            
                
    logger.info('\n\n' + 'Pipeline building completed.' + '\n\n')



    ###################### end of workflow ###########

    # Run the pipeline only if the user signifies.
    # otherwise, only construct the pipeline (above)
    if run == 1:

        try:
            workflow.write_graph(graph2use='orig')
        except:
            pass
   
   
   
        ## this section creates names for the different branched strategies.
        ## it identifies where the pipeline has forked and then appends the
        ## name of the forked nodes to the branch name in the output directory
        renamedStrats = []
        forkPoints = []
        forkPointsDict = {}

        def is_number(s):
            # function which returns boolean checking if a character
            # is a number or not
            try:
                float(s)
                return True
            except ValueError:
                return False

        for strat in strat_list:
           
            # load list of nodes in this one particular
            # strat into the list "nodeList"
            nodeList = strat.name
            renamedNodesList = []
           
            # strip the _n (n being the strat number) from
            # each node name and return to a list
            for node in nodeList:

                renamedNode = node
                lastNodeChar = node[len(node)-1]

                while lastNodeChar == '_' or lastNodeChar == '-' or is_number(lastNodeChar):
                    # make 'renamedNode' the node name with the last character
                    # stripped off, continue this until the _# at the end
                    # of it is gone - does it this way instead of just cutting
                    # off the last two characters in case of a large amount of
                    # strats which can reach double digits
                    renamedNode = renamedNode[:-1]
                    lastNodeChar = renamedNode[len(renamedNode)-1]

                   
                renamedNodesList.append(renamedNode)
               
            renamedStrats.append(renamedNodesList)
           
        # here, renamedStrats is a list containing each strat (forks)
        for strat in renamedStrats:
           
            tmpForkPoint = []
       
            # here, 'strat' is a list of node names within one of the forks
            for nodeName in strat:
               
                # compare each strat against the first one in the strat list,
                # and if any node names in the new strat are not present in
                # the 'original' one, then append to a list of 'fork points'
                for renamedStratNodes in renamedStrats:

                    if nodeName not in renamedStratNodes and \
                            nodeName not in tmpForkPoint:

                        tmpForkPoint.append(nodeName)


            forkPoints.append(tmpForkPoint)


        # forkPoints is a list of lists, each list containing node names of
        # nodes run in that strat/fork that are unique to that strat/fork

        forkNames = []

        # here 'forkPoint' is an individual strat with its unique nodes
        for forkPoint in forkPoints:
           
            forkName = ''
           
            for fork in forkPoint:

                if 'ants' in fork:
                    forklabel = 'ANTS'
                if 'fsl' in fork or 'fnirt' in fork:
                    forklabel = 'FNIRT'
                if 'automask' in fork:
                    forklabel = '3dAutoMask(func)'
                if 'bet' in fork:
                    forklabel = 'BET(func)'
                if 'bbreg' in fork:
                    forklabel = 'bbreg'
                if 'frequency' in fork:
                    forklabel = 'freq-filter'
                if 'nuisance' in fork:
                    forklabel = 'nuisance'
                if 'median' in fork:
                    forklabel = 'median'
                if 'friston' in fork:
                    forklabel = 'friston'
                if 'motion_stats' in fork:
                    forklabel = 'motion'
                if 'scrubbing' in fork:
                    forklabel = 'scrub'
                if 'slice' in fork:
                    forklabel = 'slice'

                if forklabel not in forkName:

                    forkName = forkName + '__' + forklabel
             
            forkNames.append(forkName)
   
       
           
        # match each strat_list with fork point list
        # this is for the datasink
        for x in range(len(strat_list)):
            forkPointsDict[strat_list[x]] = forkNames[x]
        
    
        '''
        Datasink
        '''
        import networkx as nx
        num_strat = 0
        sink_idx = 0
        pip_ids = []
        
        wf_names = []
        scan_ids = ['scan_anat']
        for scanID in sub_dict['rest']:
            scan_ids.append('scan_'+ str(scanID))
        
        pipes = []
        origStrat = 0
        
        for strat in strat_list:
            rp = strat.get_resource_pool()
    
            # build helper dictionary to assist with a clean strategy label for symlinks
    
            strategy_tag_helper_symlinks = {}
     
            if any('scrubbing' in name for name in strat.get_name()):
                strategy_tag_helper_symlinks['_threshold'] = 1
            else:
                strategy_tag_helper_symlinks['_threshold'] = 0
    
            if any('seg_preproc' in name for name in strat.get_name()):
                strategy_tag_helper_symlinks['_csf_threshold'] = 1
                strategy_tag_helper_symlinks['_wm_threshold'] = 1
                strategy_tag_helper_symlinks['_gm_threshold'] = 1
            else:
                strategy_tag_helper_symlinks['_csf_threshold'] = 0
                strategy_tag_helper_symlinks['_wm_threshold'] = 0
                strategy_tag_helper_symlinks['_gm_threshold'] = 0
    
    
            if any('median_angle_corr'in name for name in strat.get_name()):
                strategy_tag_helper_symlinks['_target_angle_deg'] = 1
            else:
                strategy_tag_helper_symlinks['_target_angle_deg'] = 0
    
    
            if any('nuisance'in name for name in strat.get_name()):
                strategy_tag_helper_symlinks['nuisance'] = 1
            else:
                strategy_tag_helper_symlinks['nuisance'] = 0
    
            strat_tag = ""
    
            hash_val = 0
    
            for name in strat.get_name():
                import re
                
                extra_string = re.search('_\d+', name).group(0)
                
                if extra_string:
                    name = name.split(extra_string)[0]
                
                if workflow_bit_id.get(name) != None:
                        strat_tag += name + '_'
                        
                        print name, ' ~~~ ', 2 ** workflow_bit_id[name]
                        hash_val += 2 ** workflow_bit_id[name]

    
            if p_name == None or p_name == 'None':
                
                if forkPointsDict[strat]:
                    pipeline_id = c.pipelineName + forkPointsDict[strat]
                else:
                    pipeline_id = ''
                    pipeline_id = linecache.getline(os.path.realpath(os.path.join(CPAC.__path__[0], 'utils', 'pipeline_names.py')), hash_val)
                    pipeline_id = pipeline_id.rstrip('\r\n')
                    if pipeline_id == '':
                        logger.info('hash value %s is greater than the number of words' % hash_val)
                        logger.info('resorting to crc32 value as pipeline_id')
                        pipeline_id = zlib.crc32(strat_tag)
            else:

                if forkPointsDict[strat]:
                    pipeline_id = c.pipelineName + forkPointsDict[strat]
                else:
                    pipeline_id = p_name
                    #if running multiple pipelines with gui, need to change this in future
                    p_name = None
    
            logger.info('strat_tag,  ~~~~~ , hash_val,  ~~~~~~ , pipeline_id: %s, ~~~~~ %s, ~~~~~~ %s' % (strat_tag, hash_val, pipeline_id))
            pip_ids.append(pipeline_id)
            wf_names.append(strat.get_name())
    
            for key in sorted(rp.keys()):
    
                ds = pe.Node(nio.DataSink(), name='sinker_%d' % sink_idx)
                ds.inputs.base_directory = c.outputDirectory
                ds.inputs.container = os.path.join('pipeline_%s' % pipeline_id, subject_id)
                ds.inputs.regexp_substitutions = [(r"/_sca_roi(.)*[/]", '/'),
                                                  (r"/_smooth_centrality_(\d)+[/]", '/'),
                                                  (r"/_z_score(\d)+[/]", "/"),
                                                  (r"/_dr_tempreg_maps_zstat_files_smooth_(\d)+[/]", "/"),
                                                  (r"/_sca_tempreg_maps_zstat_files_smooth_(\d)+[/]", "/"),
                                                  (r"/qc___", '/qc/')]
                node, out_file = rp[key]
                workflow.connect(node, out_file,
                                 ds, key)
                logger.info('node, out_file, key: %s, %s, %s' % (node, out_file, key))
    
    
                link_node = pe.Node(interface=util.Function(input_names=['in_file', 'strategies',
                                        'subject_id', 'pipeline_id', 'helper', 'create_sym_links'],
                                        output_names=[],
                                        function=process_outputs),
                                        name='process_outputs_%d' % sink_idx)

                link_node.inputs.strategies = strategies
                link_node.inputs.subject_id = subject_id
                link_node.inputs.pipeline_id = 'pipeline_%s' % (pipeline_id)
                link_node.inputs.helper = dict(strategy_tag_helper_symlinks)


                if 1 in c.runSymbolicLinks:             
                    link_node.inputs.create_sym_links = True
                else:
                    link_node.inputs.create_sym_links = False

    
                workflow.connect(ds, 'out_file', link_node, 'in_file')

                sink_idx += 1
                logger.info('sink index: %s' % sink_idx)
    

            d_name = os.path.join(c.outputDirectory, ds.inputs.container)
            if not os.path.exists(d_name):
                os.makedirs(d_name)
            
    
            try:
                G = nx.DiGraph()
                strat_name = strat.get_name()
                G.add_edges_from([(strat_name[s], strat_name[s + 1]) for s in range(len(strat_name) - 1)])
                dotfilename = os.path.join(d_name, 'strategy.dot')
                nx.write_dot(G, dotfilename)
                format_dot(dotfilename, 'png')
            except:
                logStandardWarning('Datasink', 'Cannot Create the strategy and pipeline graph, dot or/and pygraphviz is not installed')
                pass
    
    
            logger.info('%s*' % d_name)
            num_strat += 1
            
            pipes.append(pipeline_id)
    
    
        # creates the HTML files used to represent the logging-based status
        create_log_template(pip_ids, wf_names, scan_ids, subject_id, log_dir)
    
    
        sub_w_path = os.path.join(c.workingDirectory, wfname)
    
        if c.removeWorkingDir:
            try:
                if os.path.exists(sub_w_path):
                    import shutil
                    logger.info("removing dir -> %s" % sub_w_path)
                    shutil.rmtree(sub_w_path)
            except:
                logStandardWarning('Datasink', ('Couldn\'t remove subjects %s working directory' % wfname))
                pass

    
        logger.info('\n\n' + ('Strategy forks: %s' % pipes) + '\n\n')


        pipeline_start_date = strftime("%Y-%m-%d")
        pipeline_start_datetime = strftime("%Y-%m-%d %H:%M:%S")
        pipeline_starttime_string = pipeline_start_datetime.replace(' ','_')
        pipeline_starttime_string = pipeline_starttime_string.replace(':','-')
        
        
        '''
        # Timing code for cpac_timing_<pipeline>.txt in output directory
        timing = open(os.path.join(c.outputDirectory, 'cpac_timing_%s_%s.txt' % (c.pipelineName, pipeline_starttime_string)), 'a')
        print >>timing, "Starting CPAC run at system time: ", strftime("%Y-%m-%d %H:%M:%S")
        print >>timing, "Pipeline configuration: ", c.pipelineName
        print >>timing, "Subject workflow: ", wfname
        print >>timing, "\n"
        '''
    
    
        
        workflow.run(plugin='MultiProc', plugin_args={'n_procs': c.numCoresPerSubject})
        

        '''
        # Actually run the pipeline now
        try:

            workflow.run(plugin='MultiProc', plugin_args={'n_procs': c.numCoresPerSubject})
            
        except:
            
            crashString = "\n\n" + "ERROR: CPAC run stopped prematurely with an error - see above.\n" + ("pipeline configuration- %s \n" % c.pipelineName) + \
            ("subject workflow- %s \n\n" % wfname) + ("Elapsed run time before crash (minutes): %s \n\n" % ((time.time() - pipeline_start_time)/60)) + \
            ("Timing information saved in %s/cpac_timing_%s_%s.txt \n" % (c.outputDirectory, c.pipelineName, pipeline_starttime_string)) + \
            ("System time of start:      %s \n" % pipeline_start_datetime) + ("System time of crash: %s" % strftime("%Y-%m-%d %H:%M:%S")) + "\n\n"
            
            logger.info(crashString)
                 
            print >>timing, "ERROR: CPAC run stopped prematurely with an error."
            print >>timing, "Pipeline configuration: %s" % c.pipelineName
            print >>timing, "Subject workflow: %s" % wfname
            print >>timing, "\n" + "Elapsed run time before crash (minutes): ", ((time.time() - pipeline_start_time)/60)
            print >>timing, "System time of crash: ", strftime("%Y-%m-%d %H:%M:%S")
            print >>timing, "\n\n"
    
            timing.close()
            
            raise Exception
        '''    

    
        '''
        try:
    
            workflow.run(plugin='MultiProc', plugin_args={'n_procs': c.numCoresPerSubject})
    
        except Exception as e:
    
            print "Error: CPAC Pipeline has failed."
            print ""
            print e
            print type(e)
            ###raise Exception
        '''
    
        subject_dir = os.path.join(c.outputDirectory, 'pipeline_' + pipeline_id, subject_id)

        create_output_mean_csv(subject_dir)


        for count, scanID in enumerate(pip_ids):
            for scan in scan_ids:
                create_log_node(workflow,None, None, count, scan,log_dir).run()
            
            
    
        if 1 in c.generateQualityControlImages:
    
            for pip_id in pip_ids:
    
                f_path = os.path.join(os.path.join(c.outputDirectory, 'pipeline_' + pip_id), subject_id)
    
                f_path = os.path.join(f_path, 'qc_files_here')
    
                generateQCPages(f_path, qc_montage_id_a, qc_montage_id_s, qc_plot_id, qc_hist_id)
    
    
            ### Automatically generate QC index page
            create_all_qc.run(os.path.join(c.outputDirectory, 'pipeline_' + pip_id))       
        


        # pipeline timing code starts here

        # have this check in case the user runs cpac_runner from terminal and
        # the timing parameter list is not supplied as usual by the GUI
        if pipeline_timing_info != None:

            # pipeline_timing_info list:
            #  [0] - unique pipeline ID
            #  [1] - pipeline start time stamp (first click of 'run' from GUI)
            #  [2] - number of subjects in subject list
            unique_pipeline_id = pipeline_timing_info[0]
            pipeline_start_stamp = pipeline_timing_info[1]
            num_subjects = pipeline_timing_info[2]
        
            # elapsed time data list:
            #  [0] - elapsed time in minutes
            elapsed_time_data = []

            elapsed_time_data.append(int(((time.time() - pipeline_start_time)/60)))


            # elapsedTimeBin list:
            #  [0] - cumulative elapsed time (minutes) across all subjects
            #  [1] - number of times the elapsed time has been appended
            #        (effectively a measure of how many subjects have run)



            # needs to happen:
                 # write more doc for all this
                 # warning in .csv that some runs may be partial
                 # code to delete .tmp file


            timing_temp_file_path = os.path.join(c.outputDirectory, '%s_pipeline_timing.tmp' % unique_pipeline_id)

            if not os.path.isfile(timing_temp_file_path):
                elapsedTimeBin = []
                elapsedTimeBin.append(0)
                elapsedTimeBin.append(0)
                
                with open(timing_temp_file_path, 'wb') as handle:
                    pickle.dump(elapsedTimeBin, handle)


            with open(timing_temp_file_path, 'rb') as handle:
                elapsedTimeBin = pickle.loads(handle.read())

            elapsedTimeBin[0] = elapsedTimeBin[0] + elapsed_time_data[0]
            elapsedTimeBin[1] = elapsedTimeBin[1] + 1

            with open(timing_temp_file_path, 'wb') as handle:
                pickle.dump(elapsedTimeBin, handle)

            # this happens once the last subject has finished running!
            if elapsedTimeBin[1] == num_subjects:

                pipelineTimeDict = {}
                pipelineTimeDict['Pipeline'] = c.pipelineName
                pipelineTimeDict['Cores_Per_Subject'] = c.numCoresPerSubject
                pipelineTimeDict['Simultaneous_Subjects'] = c.numSubjectsAtOnce
                pipelineTimeDict['Number_of_Subjects'] = num_subjects
                pipelineTimeDict['Start_Time'] = pipeline_start_stamp
                pipelineTimeDict['End_Time'] = strftime("%Y-%m-%d_%H:%M:%S")
                pipelineTimeDict['Elapsed_Time_(minutes)'] = elapsedTimeBin[0]
                pipelineTimeDict['Status'] = 'Complete'
                
                gpaTimeFields= ['Pipeline', 'Cores_Per_Subject', 'Simultaneous_Subjects', 'Number_of_Subjects', 'Start_Time', 'End_Time', 'Elapsed_Time_(minutes)', 'Status']
                timeHeader = dict((n, n) for n in gpaTimeFields)
                
                timeCSV = open(os.path.join(c.outputDirectory, 'cpac_individual_timing_%s.csv' % c.pipelineName), 'a')
                readTimeCSV = open(os.path.join(c.outputDirectory, 'cpac_individual_timing_%s.csv' % c.pipelineName), 'rb')
                timeWriter = csv.DictWriter(timeCSV, fieldnames=gpaTimeFields)
                timeReader = csv.DictReader(readTimeCSV)
                
                headerExists = False
                for line in timeReader:
                    if 'Start_Time' in line:
                        headerExists = True
                
                if headerExists == False:
                    timeWriter.writerow(timeHeader)
                    
                timeWriter.writerow(pipelineTimeDict)
                timeCSV.close()
                readTimeCSV.close()

                # remove the temp timing file now that it is no longer needed
                os.remove(timing_temp_file_path)
        
        
        
        endString = ("End of subject workflow %s \n\n" % wfname) + "CPAC run complete:\n" + ("pipeline configuration- %s \n" % c.pipelineName) + \
        ("subject workflow- %s \n\n" % wfname) + ("Elapsed run time (minutes): %s \n\n" % ((time.time() - pipeline_start_time)/60)) + \
        ("Timing information saved in %s/cpac_individual_timing_%s.csv \n" % (c.outputDirectory, c.pipelineName)) + \
        ("System time of start:      %s \n" % pipeline_start_datetime) + ("System time of completion: %s" % strftime("%Y-%m-%d %H:%M:%S"))
    
        logger.info(endString)
    
        '''
        print >>timing, "CPAC run complete:"
        print >>timing, "pipeline configuration- %s" % c.pipelineName
        print >>timing, "subject workflow- %s" % wfname
        print >>timing, "\n" + "Elapsed run time (minutes): ", ((time.time() - pipeline_start_time)/60)
        print >>timing, "System time of completion: ", strftime("%Y-%m-%d %H:%M:%S")
        print >>timing, "\n\n"
    
        timing.close()
        '''


    return workflow




def run(config, subject_list_file, indx, strategies, \
     maskSpecificationFile, roiSpecificationFile, templateSpecificationFile, p_name = None):
    import commands
    commands.getoutput('source ~/.bashrc')
    import pickle
    import yaml


    c = Configuration(yaml.load(open(os.path.realpath(config), 'r')))

    try:
        sublist = yaml.load(open(os.path.realpath(subject_list_file), 'r'))
    except:
        raise Exception ("Subject list is not in proper YAML format. Please check your file")

    sub_dict = sublist[int(indx) - 1]


    c.maskSpecificationFile = maskSpecificationFile
    c.roiSpecificationFile = roiSpecificationFile
    c.templateSpecificationFile = templateSpecificationFile

    
    prep_workflow(sub_dict, c, pickle.load(open(strategies, 'r')), 1, p_name)

