#! /usr/bin/env python3

#
# EMU2_reader.py -- Copyright (C) 2016 Stephen Makonin
#
# 2024-04 Added Time of Use calculations to automatically set the manual price in the EMU-2

import os, sys, platform, time, datetime, serial
import requests
import xml.etree.ElementTree as et

import datetime
import time


price_to_compare=0.09997
on_peak_multiplier = 1.8632
off_peak_multiplier = 0.7821
super_off_peak_multiplier = 0.5749
distribution_charge=0.043412+0.004430

# Define the TOU pricing periods
pricing_periods = {
    "On-Peak": (datetime.time(14, 0), datetime.time(21, 0)),
    "Super Off-Peak": ((datetime.time(23, 0), datetime.time(0, 0)),(datetime.time(0, 0), datetime.time(6, 0))),
    "Off-Peak": ((datetime.time(0, 0), datetime.time(6, 0)), (datetime.time(9, 0), datetime.time(14, 0)), (datetime.time(21, 0), datetime.time(23, 0)))
}

current_period = None



def setPrice(period):
    
        # Calculate the price based on the period
    if period == "On-Peak":
        price = price_to_compare * on_peak_multiplier + distribution_charge
    elif period == "Off-Peak":
        price = price_to_compare * off_peak_multiplier + distribution_charge
    elif period == "Super Off-Peak":
        price = price_to_compare * super_off_peak_multiplier + distribution_charge
    else:
        price = price_to_compare + distribution_charge  # Default to normal price if period is not recognized
        
    print(f"Switching to {period} period. Price is ${price}.")

    # Convert price to hexadecimal
    price_hex = hex(int(price * 1e5))[2:].zfill(6)  # Multiply by 100 to convert to cents, then convert to hex

    # Create the command string
    command_string = f"<Command><Name>set_current_price</Name><Price>0x{price_hex}</Price><TrailingDigits>0x05</TrailingDigits></Command>"
    print(command_string)
    emu2.write(command_string.encode(encoding="ascii"))

def is_weekend():
    return datetime.datetime.today().weekday() in [5, 6]  # 5 is Saturday, 6 is Sunday

def check_period():
    global current_period
    now = datetime.datetime.now().time()
    if is_weekend():
        if now >= pricing_periods["Super Off-Peak"][0] or now < pricing_periods["Super Off-Peak"][1]:
            period = "Super Off-Peak"
        else:
            period = "Off-Peak"
    else:
        for period, times in pricing_periods.items():
            if isinstance(times[0], tuple):  # For Off-Peak which has multiple time ranges
                for start, end in times:
                    if start <= now <= end:
                        break
                else:
                    continue
                break
            else:
                start, end = times
                if start <= now <= end:
                    break
        else:
            period = "Off-Peak"
    if period != current_period:
        setPrice(period)
        current_period = period

def open_serial_port():
    port_list = ['/dev/ttyACM0', '/dev/ttyACM1']
    
    for port in port_list:
        try:
            ser = serial.Serial(port, 115200, timeout=1)
            print(f"Opened serial port: {port}")
            return ser
        except serial.SerialException:
            print(f"Failed to open serial port: {port}")
            continue
    
    print("Failed to open any serial port")
    return None



#domain = "192.168.1.100"
domain = "192.168.1.100:8080"
emoncmspath = ""
apikey = "xxxx"
nodeid = "power"

print()
print('Read your Rainforest EMU2 device:')
print()


emu2 = open_serial_port()
  

try:
    delivered_ts = demand_ts = 0
    while True:
        check_period()
        msg = emu2.readlines()
        if msg == [] or msg[0].decode()[0] != '<':
            continue     
        
        msg = ''.join([line.decode() for line in msg])
        print(msg)
        try:
            tree = et.fromstring(msg)
        except:
            continue
                    
        if tree.tag == 'InstantaneousDemand':
            ts = int(tree.find('TimeStamp').text, 16)
            diff = ts - demand_ts
            demand_ts = ts
            
            demand = tree.find('Demand').text
            demand = int.from_bytes(bytes.fromhex(demand[2:]), byteorder="big", signed=True)
            power = demand #int(tree.find('Demand').text, 16)
            power *= int(tree.find('Multiplier').text, 16)
            power /= int(tree.find('Divisor').text, 16)
            power = round(power, int(tree.find('DigitsRight').text, 16))
            print('Message:', tree.tag, '- Apparent Power = ', power, 'kW', '(delay', diff, 's).')
            request = "http://"+domain+"/"+emoncmspath+"input/post.json?apikey="+apikey+"&node="+str(nodeid)+"&json={InstantPower:"+str(power)+"}"
#            print(request)
            try:
                r = requests.get(request,timeout=3)
                r.raise_for_status()
            except requests.exceptions.HTTPError as errh:
                print ("Http Error:",errh)
            except requests.exceptions.ConnectionError as errc:
                print ("Error Connecting:",errc)
            except requests.exceptions.Timeout as errt:
                print ("Timeout Error:",errt)
            except requests.exceptions.RequestException as err:
                print ("OOps: Something Else",err)
        elif tree.tag == 'CurrentSummationDelivered':
            ts = int(tree.find('TimeStamp').text, 16)
            diff = ts - delivered_ts
            delivered_ts = ts
            SummationDelivered = tree.find('SummationDelivered').text
            SummationDelivered = int.from_bytes(bytes.fromhex(SummationDelivered[2:]), byteorder="big", signed=True)
            SummationReceived = tree.find('SummationReceived').text
            SummationReceived = int.from_bytes(bytes.fromhex(SummationReceived[2:]), byteorder="big", signed=True
            energy = SummationDelivered
            energy -= SummationReceived
            energy *= int(tree.find('Multiplier').text, 16)
            energy /= int(tree.find('Divisor').text, 16)
            energy = round(energy, int(tree.find('DigitsRight').text, 16))
            print('Message:', tree.tag, '- Net Apparent Energy = ', energy, 'kWh', '(delay', diff, 's).')
            request = "http://"+domain+"/"+emoncmspath+"input/post.json?    apikey="+apikey+"&node="+str(nodeid)+"&json={MeterTotal:"+str(energy)+"}"
#            print(request)
            try:
                r = requests.get(request.strip(),timeout=3)
                r.raise_for_status()
            except requests.exceptions.HTTPError as errh:
                print ("Http Error:",errh)
            except requests.exceptions.ConnectionError as errc:
                print ("Error Connecting:",errc)
            except requests.exceptions.Timeout as errt:
                print ("Timeout Error:",errt)
            except requests.exceptions.RequestException as err:
                print ("OOps: Something Else",err)
        else:
            print()
            print('Message:', tree.tag)
            for child in tree:
                value = int(child.text, 16) if child.text[:2] == '0x' else child.text
                print('\t', child.tag, '=', value)
            print()
            
except KeyboardInterrupt:
    print()
    print('User break signaled!')
    print()
    emu2.close()    
    sys.exit(0)

