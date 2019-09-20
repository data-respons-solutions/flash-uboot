#!/usr/bin/env python3

import sys, errno, os, subprocess, hashlib, argparse

mtd_path = '/proc/mtd'

def get_partitioning():
    with open(mtd_path, "r") as mtd:
        slist = mtd.read().splitlines()
        slist.pop(0)
        partitions = []
        
    for s in slist:
        dev = '/dev/' + s.split(' ')[0].strip(':')
        size = '0x' +  s.split(' ')[1]
        name = s.split(' ')[3].strip('\"')
        partitions.append([dev, size, name])
        
    return partitions

def get_hexdigest(name, offset, length):
  with open(name, "rb") as f:
    f.seek(offset)
    buf = f.read(length);
    h = hashlib.md5()
    h.update(buf);
    return h.hexdigest()

def check_same(dev, dev_offset, file):
    statf = os.stat(file)
    file_hexdigest = get_hexdigest(file, 0, statf.st_size)
    dev_hexdigest = get_hexdigest(dev, dev_offset, statf.st_size)

    if file_hexdigest != dev_hexdigest:
        print('{}: {}'.format(file_hexdigest, file))
        print('{}: {}'.format(dev_hexdigest, dev))
        return False
    
    return True

def set_gpio(gpio, state):
  stdout = open('/sys/class/gpio/' + gpio + '/value', "w")
  subprocess.call(['/bin/echo', str(state)], stdout=stdout)

def enable_write(gpio):
    set_gpio(gpio, 0)
    
def disable_write(gpio):
    set_gpio(gpio, 1)

def write_flash(dev, offset, file):
  statf = os.stat(file)
  with open(file, 'rb') as f:
    buf = f.read(statf.st_size);
    
  with open(dev, 'wb') as d:
    d.seek(offset)
    d.write(buf)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='u-boot programmer', prog='flash-uboot')
    parser.add_argument('--spl', help='SPL binary')
    parser.add_argument('--uboot', help='u-boot binary')
    parser.add_argument('--gpio', help='Flash write protect gpio')
    args = parser.parse_args()
        
    if not (args.spl or args.uboot):
        print('{}: --uboot or --spl must be set'.format(parser.prog))
        parser.print_usage()
        sys.exit(1)  
    
    for file in [args.spl, args.uboot]:
        if file and not os.path.isfile(file):
            print('{}: {} not found'.format(parser.prog, file))
            sys.exit(1)
    
    partitions = get_partitioning()
    print('Found {} partitions in {}'.format(len(partitions), mtd_path))
    for dev, size, name in partitions:
        print(dev, size, name)

    targets = []
    if args.spl:
        targets.append(['spl', 0x400, args.spl])
        
    if args.uboot:
        targets.append(['u-boot', 0x0, args.uboot])
        
    print('Check if update is needed')
    for label, offset, file in targets:
        for dev, size, name in partitions:
            if name == label:
                if not check_same(dev, offset, file):
                    print('{}: NEED TO FLASH'.format(label))
                    try:
                        if args.gpio:
                            enable_write(args.gpio)
                            subprocess.check_call(['/usr/sbin/flash_erase', dev, '0', '0'])
                            print('{}: ERASED'.format(label))
                            write_flash(dev, offset, file)
                            if check_same(dev, offset, file):
                                print('{}: UPDATED'.format(label))
                            else:
                                print('{}: FAILED'.format(label))
                                sys.exit(1)
                    finally:
                        if args.gpio:
                            disable_write(args.gpio)
                        
    sys.exit(0)
    