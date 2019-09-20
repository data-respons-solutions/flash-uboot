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

class mmc_device(object):
    def __init__(self, device, spl_offset, uboot_offset):
        self.dev = device
        self.size = int(subprocess.run(['blockdev', '--getsize64', device],
                                        check=True, capture_output=True).stdout)
        self.sections = {
            'spl' : {
                'offset' : spl_offset,
                },
            'uboot' : {
                'offset' : uboot_offset,
                },
            }

    def has_section(self, section):
        return (section in self.sections)
    
    def erase_section(self, section):
        pass
    
    def size(self, section):
        return abs(self.size, self.sections[section]['offset'])
    
    def read(self, section, size):
        return get_buf(self.dev, self.sections[section]['offset'], size)
    
    def write(self, section, buf):
        with open(f'/sys/block/os.path.basename(self.dev)/force_ro', 'r+') as lock:
            # enable write
            lock.write('0')
            try:
                with open(self.dev, 'wb') as f:
                    f.seek(self.sections[section]['offset'])
                    f.write(buf)
                    f.flush()
            finally:
                lock.write('1')

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
        subprocess.run(['/usr/sbin/flash_erase', self.partitions[section]['dev'], '0', '0'],
                            check=True, capture_output=True)
    
    def size(self, section):
        return abs(self.partitions[section]['size'], self.partitions[section]['offset'])
    
    def read(self, section, size):
        return get_buf(self.partitions[section]['dev'], self.partitions[section]['offset'], size)
    
    def write(self, section, buf):
        with open(self.partitions[section]['dev'], 'wb') as f:
            f.seek(self.partitions[section]['offset'])
            f.write(buf)

def parse_version(buf):
    max_length = 1024
    min_length = 15
    not_found = 'UNAVAILABLE'
    version_token = str.encode('U-Boot')
    try:
        end = -1
        while True:
            start = buf.index(version_token, end + 1)
            end = buf.index(b'\x00', start + 1)
            if (end - start) <= max_length and (end - start) > min_length:
                try:
                    return buf[start:end].decode().strip('\n')
                except:
                    start = buf.index(version_token, end + 1)       
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
    parser.add_argument('--get-version', help=\
                        'Read version string from flash section. Available sections: "uboot", "spl"')
    parser.add_argument('--get-file-version', help='Read version string from file')
    parser.add_argument('--write', action='store_true', help='Write to flash')
    parser.add_argument('--verify', action='store_true', help='Verify only, ignores write flag')
    parser.add_argument('--spl', help='SPL binary')
    parser.add_argument('--spl-offset', default=0, type=hex_int, help='SPL offset in flash')
    parser.add_argument('--uboot', help='u-boot binary')
    parser.add_argument('--uboot-offset', default=0, type=hex_int, help='u-boot offset in flash')
    parser.add_argument('--gpio', type=int, help='Flash write protect gpio number')
    args = parser.parse_args()

    for file in [args.spl, args.uboot, args.get_file_version]:
            if file and not os.path.isfile(file):
                print(f'file not found: {file}', file=sys.stderr)
                sys.exit(1)
    
    if not (args.get_file_version or args.get_version):
        if not (args.spl or args.uboot):
            print('uboot binary not provided (--uboot and/or --spl)', file=sys.stderr)
            sys.exit(1)
            
        if (args.mtd and args.mmc) or not (args.mtd or args.mmc):
            print('Select one(and only one) flash device', file=sys.stderr)
            sys.exit(1)        
        
    data = {}

    ''' get file version '''
    if args.get_file_version:
        file = create_file_data(args.get_file_version)
        print(parse_version(file["buf"]))
        sys.exit(0)
        
        
    ''' get flash device '''
    if args.mtd:
        data['flash'] = mtd_device(args.spl_offset, args.uboot_offset)
        
    ''' get version from flash '''
    if args.get_version:
        if not data['flash'].has_section(args.get_version):
            print(f'No section "{args.get_version}" in flash', file=sys.stderr)
            sys.exit(1)
            
        print(get_version(data["flash"], args.get_version))
        sys.exit(0)
    
    ''' get input files '''
    if args.spl:
        data['spl'] = create_file_data(args.spl)
    if args.uboot:
        data['uboot'] = create_file_data(args.uboot)
        
    ''' verify '''
    for section in ('spl', 'uboot'):
        if section in data:
            if not flash.has_section(section):
                print(f'flash: {section} defined but section not detected in flash {flash}', file=sys.stderr)
                sys.exit(1)
            
            if data[section]['size'] > flash.size(section):
                print(f'flash: {section} file ({data[section]["size"]}b) larger than flash section ({flash.size(section)}b)')
                sys.exit(1)
                
            flash_section_md5 = get_md5(flash.read(section, data[section]['size']))

            if data[section]['md5'] != flash_section_md5:
                print(f'flash: {section}: NEED TO FLASH: {data[section]["size"]}b: file ({data[section]["md5"]}) != flash ({flash_section_md5})')
                data[section]['need_to_flash'] = True
            else:
                print(f'flash: {section}: ok: {data[section]["size"]}b: file ({data[section]["md5"]}) == flash ({flash_section_md5})')         
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
                        print(f'flash: {section}: FLASHING')
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
 