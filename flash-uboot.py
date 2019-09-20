#!/usr/bin/python3

import sys
import os
import hashlib
import argparse
import subprocess

def set_gpio(gpio, state):   
    with open(f'/sys/class/gpio/gpio{gpio}/value', 'w') as f:
        f.write(str(int(state)))

def get_md5(buf):
    h = hashlib.md5()
    h.update(buf)
    return h.hexdigest()

def get_buf(file, offset, size):
    with open(file, 'rb') as f:
        f.seek(offset)
        return f.read(size)

def create_file_data(file):
    data = {}
    data['file'] = file
    data['size'] = os.stat(file).st_size
    data['buf'] = get_buf(data['file'], 0, data['size'])
    data['md5'] = get_md5(data['buf'])
    return data

class mtd_device(object):
    def __init__(self, spl_offset, uboot_offset):    
        self.partitions = {}
        
         # Read partition data 
        with open('/proc/mtd', 'r') as mtd:
            slist = mtd.read().splitlines()
            slist.pop(0)
    
        # Find uboot and spl partitions
        for s in slist:
            dev = '/dev/' + s.split(' ')[0].strip(':')
            size = int('0x' +  s.split(' ')[1], 0)
            name = s.split(' ')[3].strip('\"')
            if name == 'u-boot':
                self.partitions['uboot'] = {
                    'dev' : dev,
                    'size' : size,
                    'offset' : uboot_offset,
                    }
            elif name == 'spl':
                self.partitions['spl'] = {
                    'dev' : dev,
                    'size' : size,
                    'offset' : spl_offset,
                    }
    def has_section(self, section):
        return (section in self.partitions)
    
    def erase_section(self, section):
        subprocess.check_call(['/usr/sbin/flash_erase', self.partitions[section]['dev'], '0', '0'])

    def offset(self, section):
        return self.partitions[section]['offset']
    
    def size(self, section):
        return self.partitions[section]['size']
    
    def read(self, section, size):
        return get_buf(self.partitions[section]['dev'], self.partitions[section]['offset'], size)
    
    def write(self, section, buf):
        with open(self.partitions[section]['dev'], 'wb') as f:
            f.seek(self.partitions[section]['offset'])
            f.write(buf)

def parse_version(buf):
    max_length = 1024
    not_found = 'UNAVAILABLE'
    version_token = str.encode('U-Boot')
    try:
        start = buf.index(version_token)       
        end = buf.index(b'\x00', start + 1)
        if (end - start) > max_length:
            return not_found
        return buf[start:end].decode().strip('\n')
    except:
        pass
    return not_found
    
def get_version(flash, section):
    buf = flash.read(section, flash.size(section))
    return parse_version(buf)
    
def hex_int(x):
    return int(x, 0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='u-boot programmer')
    parser.add_argument('--mtd', action='store_true', help='uboot located in mtd device')
    parser.add_argument('--mmc', help='uboot located in mmc device')
    parser.add_argument('--get-version', action='append', help=\
                        'Read version string from flash. Define this argument for every section to read. Available sections: "uboot", "spl"')
    parser.add_argument('--write', action='store_true', help='Write to flash')
    parser.add_argument('--verify', action='store_true', help='Verify only, ignores write flag')
    parser.add_argument('--spl', help='SPL binary')
    parser.add_argument('--spl-offset', default=0, type=hex_int, help='SPL offset in flash')
    parser.add_argument('--uboot', help='u-boot binary')
    parser.add_argument('--uboot-offset', default=0, type=hex_int, help='u-boot offset in flash')
    parser.add_argument('--gpio', type=int, help='Flash write protect gpio number')
    args = parser.parse_args()

    if not (args.spl or args.uboot or args.get_version):
        print('uboot binary not provided (--uboot and/or --spl)', file=sys.stderr)
        sys.exit(1)
    else:
        for file in [args.spl, args.uboot]:
            if file and not os.path.isfile(file):
                print(f'{file} not found', file=sys.stderr)
                sys.exit(1)

    if not (args.mtd or args.mmc or args.get_version):
        print('flash location not defined (--mtd and/or --mmc)', file=sys.stderr)
        sys.exit(1)
    
    data = {'flash' : {}}
    if args.spl:
        data['spl'] = create_file_data(args.spl)
    if args.uboot:
        data['uboot'] = create_file_data(args.uboot)
    if args.mtd:
        data['flash']['mtd'] = mtd_device(args.spl_offset, args.uboot_offset)
    if args.mmc:
        data['flash']['mmc'] = {
            'device' : args.mmc,
            }
    
    ''' get version '''
    if args.get_version:
        for section in args.get_version:
            for name, flash in data['flash'].items():
                if not flash.has_section(section):
                    print(f'{name}: section "{section}" not available', file=sys.stderr)
                    sys.exit(1)
                    
        for section in args.get_version: 
            for name, flash in data['flash'].items():
                print(f'{name}: {section}: version: "{get_version(flash, section)}"')

            if section in data:
                print(f'file: {section}: version "{parse_version(data[section]["buf"])}"')

        sys.exit(0)
                
    ''' verify '''
    for section in ('spl', 'uboot'):
        if section in data:
            for name, flash in data['flash'].items():
                if not flash.has_section(section):
                    print(f'{name}: {section} defined but section not detected in flash {flash}', file=sys.stderr)
                    sys.exit(1)
                
                flash_section_size = flash.size(section) - flash.offset(section)
                if data[section]['size'] > flash_section_size:
                    print(f'{name}: {section} file ({data[section]["size"]}b) larger than flash section ({flash_section_size}b)')
                    sys.exit(1)
                    
                flash_section_md5 = get_md5(flash.read(section, data[section]['size']))

                if data[section]['md5'] != flash_section_md5:
                    print(f'{name}: {section}: NEED TO FLASH: {data[section]["size"]}b: file ({data[section]["md5"]}) != flash ({flash_section_md5})')
                    data[section]['need_to_flash'] = True
                else:
                    print(f'{name}: {section}: ok: {data[section]["size"]}b: file ({data[section]["md5"]}) == flash ({flash_section_md5})')         
    if args.verify:
        # We check if any section was not identical. Return 1 if mismatch found
        for section in ('spl', 'uboot'):
            if section in data:
                if 'need_to_flash' in data[section] and data[section]['need_to_flash']:
                    sys.exit(1)
        sys.exit(0)
    
    ''' write '''
    if args.write:
        for section in ('spl', 'uboot'):
            if section in data:
                if 'need_to_flash' in data[section] and data[section]['need_to_flash']:
                    for name, flash in data['flash'].items():
                        print(f'{name}: {section}: FLASH')
                        if args.gpio:
                            # enable write
                            set_gpio(args.gpio, False)
                        try:
                            flash.erase_section(section)
                            flash.write(section, data[section]['buf'])  
                        finally:
                            if args.gpio:
                                # disable write
                                set_gpio(args.gpio, True)

    sys.exit(0)
 