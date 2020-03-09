#!/usr/bin/env python
"""Print PCB layers

This program runs pcbnew and then uses the File|Print menu to print the desired
layers.
The process is graphical and very delicated.
"""

__author__   ='Salvador E. Tropea'
__copyright__='Copyright 2019-2020, INTI/Productize SPRL'
__credits__  =['Salvador E. Tropea','Scott Bezek']
__license__  ='Apache 2.0'
__email__    ='salvador@inti.gob.ar'
__status__   ='beta'

import sys
import os
import logging
import argparse
import atexit
import time
import re

import subprocess
import gettext

# Look for the 'util' module from where the script is running
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))
# Utils import
# Log functionality first
from util import log
log.set_domain(os.path.splitext(os.path.basename(__file__))[0])
from util import file_util
from util.misc import (REC_W,REC_H,__version__)
from util.ui_automation import (
    PopenContext,
    xdotool,
    wait_focused,
    wait_not_focused,
    wait_for_window,
    recorded_xvfb,
    clipboard_store
)

def dismiss_already_running():
    # The "Confirmation" modal pops up if pcbnew is already running
    try:
        nf_title = 'Confirmation'
        wait_for_window(nf_title, nf_title, 1)

        logger.info('Dismiss pcbnew already running')
        xdotool(['search', '--onlyvisible', '--name', nf_title, 'windowfocus'])
        xdotool(['key', 'Return'])
    except RuntimeError:
        pass

def dismiss_warning():
    try:
        nf_title = 'Warning'
        wait_for_window(nf_title, nf_title, 1)

        logger.error('Dismiss pcbnew warning, will fail')
        xdotool(['search', '--onlyvisible', '--name', nf_title, 'windowfocus'])
        xdotool(['key', 'Return'])
    except RuntimeError:
        pass

def dismiss_pcbNew_Error():
    try:
        nf_title = 'pcbnew Error'
        wait_for_window(nf_title, nf_title, 3)

        logger.error('Dismiss pcbnew error')
        xdotool(['search', '--onlyvisible', '--name', nf_title, 'windowfocus'])
        logger.error('Found, sending Return')
        xdotool(['key', 'Return'])
    except RuntimeError:
        pass

def print_layers(pcb_file, output_dir, output_filename, record=True):

    file_util.mkdir_p(output_dir)

    print_output_file = os.path.join(os.path.abspath(output_dir), output_filename)
    if os.path.exists(print_output_file):
        os.remove(print_output_file)

    xvfb_kwargs = { 'width': args.rec_width, 'height': args.rec_height, 'colordepth': 24, }

    with recorded_xvfb(output_dir if record else None, 'pcbnew_print_layers_screencast.ogv', **xvfb_kwargs):
        with PopenContext(['pcbnew', pcb_file], stderr=open(os.devnull, 'wb'), close_fds=True) as pcbnew_proc:

            clipboard_store(print_output_file)

            #dismiss_pcbNew_Error()

            failed_focuse = False
            try:
               wait_for_window('Main pcbnew window', 'Pcbnew', 25)
            except RuntimeError:
               failed_focuse = True
               pass
            if failed_focuse:
               dismiss_already_running()
               dismiss_warning()
               wait_for_window('Main pcbnew window', 'Pcbnew', 5)

            logger.info('Open File->Print')
            xdotool(['key', 'alt+f', 'p'])

            id=wait_for_window('Print dialog', 'Print')
            # The color option is selected (not with a WM)
            xdotool(['key', 'Tab',  'Tab',  'Tab',  'Tab',  'Tab',  'Tab',  'Tab',  'Tab', 'Return'])

            id2 = wait_for_window('Printer dialog', '^(Print|%s)$' % print_dlg_name, skip_id=id[0])
            # List of printers
            xdotool(['key', 'Tab',
                    # Go up to the top
                    'Home',
                    # Output file name
                    'Tab',
                    # Open dialog
                    'Return'])
            id_sel_f = wait_for_window('Select a filename', '(Select a filename|%s)' % select_a_filename, 2)
            logger.info('Pasting output dir')
            xdotool(['key',
                    # Select all
                    'ctrl+a',
                    # Paste
                    'ctrl+v',
                    # Select this name
                    'Return'])
            # Back to print
            wait_not_focused(id_sel_f[0])
            wait_for_window('Printer dialog', '^(Print|%s)$' % print_dlg_name, skip_id=id[0])
            xdotool(['key',
                    # Format options
                    'Tab',
                    # Be sure we are at left (PDF)
                    'Left','Left','Left',
                    # Print it
                    'Return'])

            file_util.wait_for_file_created_by_process(pcbnew_proc.pid, print_output_file)

            wait_not_focused(id2[1])
            id=wait_for_window('Print dialog', 'Print')
            # Close button
            xdotool(['key', 'Tab',  'Tab',  'Tab',  'Tab',  'Tab',  'Tab',  'Tab',  'Tab', 'Tab', 'Tab', 'Return'])

            wait_not_focused(id2[0])
            wait_for_window('Main pcbnew window', 'Pcbnew')
            pcbnew_proc.terminate()

    return print_output_file

# Restore the pcbnew configuration
def restore_config():
    if os.path.exists(old_config_file):
       os.remove(config_file)
       os.rename(old_config_file,config_file)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='KiCad automated PCB printer')

    parser.add_argument('kicad_pcb_file', help='KiCad schematic file')
    parser.add_argument('output_dir', help='Output directory')
    parser.add_argument('layers', nargs='+', help='Which layers to include')
    parser.add_argument('--record','-r',help='Record the UI automation',action='store_true')
    parser.add_argument('--rec_width',help='Record width ['+str(REC_W)+']',type=int,default=REC_W)
    parser.add_argument('--rec_height',help='Record height ['+str(REC_H)+']',type=int,default=REC_H)
    parser.add_argument('--output_name','-o',nargs=1,help='Name of the output file',default=['printed.pdf'])
    parser.add_argument('--verbose','-v',action='count',default=0)
    parser.add_argument('--version','-V',action='version', version='%(prog)s '+__version__+' - '+
                        __copyright__+' - License: '+__license__)

    args = parser.parse_args()

    # Create a logger with the specified verbosity
    logger = log.init(args.verbose)

    # Get local versions for the GTK window names
    gettext.textdomain('gtk30')
    select_a_filename=gettext.gettext('Select a filename')
    print_dlg_name=gettext.gettext('Print')
    logger.debug('Select a filename -> '+select_a_filename)
    logger.debug('Print -> '+print_dlg_name)

    # Force english + UTF-8
    os.environ['LANG'] = 'C.UTF-8'

    # Read the layer names from the PCB
    layer_names=['-']*50
    pcb_file = open(args.kicad_pcb_file,"r")
    collect_layers=False
    for line in pcb_file:
        if collect_layers:
           z=re.match('\s+\((\d+)\s+(\S+)',line)
           if z:
              res=z.groups()
              #print(res[1]+'->'+res[0])
              layer_names[int(res[0])]=res[1]
           else:
              if re.search('^\s+\)$',line):
                 collect_layers=False
                 break
        else:
           if re.search('\s+\(layers',line):
              collect_layers=True
    pcb_file.close()

    # Back-up the current pcbnew documentation
    config_file = os.environ['HOME'] + '/.config/kicad/pcbnew'
    old_config_file = config_file + '.pre_print_layers'
    os.rename(config_file,old_config_file)
    atexit.register(restore_config)

    # Create a suitable configuration
    text_file = open(config_file,"w")
    text_file.write('canvas_type=2\n')
    text_file.write('RefillZonesBeforeDrc=1\n')
    text_file.write('PcbFrameFirstRunShown=1\n')
    # Color
    text_file.write('PrintMonochrome=0\n')
    # Include frame
    text_file.write('PrintPageFrame=1\n')
    # Real drill marks
    text_file.write('PrintPadsDrillOpt=2\n')
    # Only one file
    text_file.write('PrintSinglePage=1\n')
    # Mark which layers are requested
    used_layers=[0]*50
    for layer in args.layers:
        try:
            used_layers[layer_names.index(layer)]=1
        except:
            print('Unknown layer %s' % layer)
    # List all posible layers, indicating which ones are requested
    for x in range(0,50):
        text_file.write('PlotLayer_%d=%d\n' % (x,used_layers[x]))
    text_file.close()

    print_layers(args.kicad_pcb_file, args.output_dir, args.output_name[0], args.record)

    