# -*- coding:utf-8 -*-
import json
import logging
import struct
import threading
import os, sys
import string
import socket
from time import ctime,sleep,time,strftime,localtime
import httplib2
from urllib import urlencode
import networkx as nx
from Queue import Queue
import xml.dom.minidom
from operator import attrgetter
from ryu import cfg
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import ipv6
from ryu.lib.packet import arp
from ryu.lib import hub
import multhreading_new
from webob import Response
from ryu.app.wsgi import ControllerBase, WSGIApplication, route

simple_WIAPA_instance_name = 'simple_WIAPA_api_app'
url = '/simpleWIAPA/commands'



class WIAPAnetwork(object):

    def __init__(self, deviceinfo, topology, panID, ipaddress = None):
        self.deviceinfo = deviceinfo
        self.topology = topology
        self.panID = panID
        self.graph = nx.DiGraph()
        self.pathlist = [] #路径列表
        self.routeIDlist = {} #{path:routeID,.....}
        self.ipaddress = ipaddress
        self.macaddress = None

    def get_panID(self):
        return self.panID
    def get_deviceinfo(self):
        return self.deviceinfo
    def get_topology(self):
        return self.topology
    def get_routeID(self, path):

        for key in self.pathlist:
            if isinstance(path, list) and path == key:
                return self.routeIDlist[tuple(key)]
            if isinstance(path, str) and path == key[0]:
                return self.routeIDlist[tuple(key)]

        return None

    def set_deviceinfo(self, deviceinfo):
        self.deviceinfo = deviceinfo
    def set_topology(self, topology):
        self.topology = topology

    def routeID_calculation(self, path):

        if(path[0] == "0001"):
            if (self.deviceinfo[path[-1]] == "2"):
                routeID_down = (((int(path[-1], 16) << 1) >> 8) - 1) << 8
                routeID_up = (int(path[-1], 16) << 1)
            if (self.deviceinfo[path[-1]] == "3"):
                routeID_down = (int(path[-1], 16) & 0xff00) | (((int(path[-1], 16) << 1) - 1) & 0x00ff)
                routeID_up = (int(path[-1], 16) & 0xff00) | ((int(path[-1], 16) << 1) & 0x00ff)
        else:
            print "路径起始地址错误！"

        self.routeIDlist[tuple(path)] = [routeID_up, routeID_down]

    def shortest_path_creat(self, target):

        for key in self.topology:
            self.graph.add_edge(key[0], key[1], weight=1)
        for key in self.deviceinfo:
            if self.deviceinfo[key] == "1":
                generator = nx.shortest_simple_paths(self.graph, source=key,
                                                     target=target, weight='weight')
                path = []
                k = 1
                try:
                    for path in generator:
                        if k <= 0:
                            break
                        k -= 1
                        print("PATH: %s" % path)
                        self.pathlist.append(path)
                        self.routeID_calculation(path)
                except:
                    print("No path between %s and %s" % (key, target))
class WIAPAScheduling(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}
    def __init__(self, *args, **kwargs):
        super(WIAPAScheduling, self).__init__(*args, **kwargs)
        self.msg = None
        self.q = []
        self.req = []
        self.panid = [] #系统管理器IP地址
        self.shortaddr = []
        self.topo = []
        self.schedulinginfo = {}
        self.WIAPAobject = []
        wsgi = kwargs['wsgi']
        wsgi.register(SimpleWIAPAController, {simple_WIAPA_instance_name : self})
        t = threading.Thread(target = self.TCPServer,args=(self.q,self.req,1))
        t.start()
#        print "%s" %self.q

    @set_ev_cls(ofp_event.EventWIAPACommandIn, MAIN_DISPATCHER)
    def get_command_info( self, ev ):
        flag = 0
        flag1 = 0
        msg = ev.msg
        print "%s" %msg
        for key in self.panid:
            if(key == msg['src']['ip']):
                flag = 1
            if(key == msg['dst']['ip']):
                flag1 = 1
        if(flag != 1 or flag1 != 1):
            print "不存在的网络"
            return
        print "获取PANID为%s的WIA-PA网络的信息" %msg['src']['panid']
        res = self.getWIAPAobject(msg['src'])
        if(res == -1):
            print "获取PANID为%s的WIA-PA网络的信息失败！" % msg['src']['panid']
            return
        print "获取PANID为%s的WIA-PA网络的信息" %msg['dst']['panid']
        res = self.getWIAPAobject(msg['dst'])
        if (res == -1):
            print "获取PANID为%s的WIA-PA网络的信息失败！" % msg['src']['panid']
            return
        print "计算路径"
        print "生成映射表"
        self.schedulinginfo[(self.WIAPAobject[int(msg['src']['panid'])].ipaddress, \
                             self.WIAPAobject[int(msg['src']['panid'])].macaddress, \
                             tuple(self.WIAPAobject[int(msg['src']['panid'])].get_routeID('0001')))] = \
            (self.WIAPAobject[int(msg['dst']['panid'])].ipaddress, \
             self.WIAPAobject[int(msg['dst']['panid'])].macaddress, \
             tuple(self.WIAPAobject[int(msg['dst']['panid'])].get_routeID('0001')))
        for key in self.schedulinginfo:
            print(key, 'corresponds to', self.schedulinginfo[key])

        print "生成路由表"
        for key in self.WIAPAobject[int(msg['src']['panid'])].deviceinfo:
            if (self.WIAPAobject[int(msg['src']['panid'])].deviceinfo[key] == '2'):
                routetable = self.createRoutetable(key, self.WIAPAobject[int(msg['src']['panid'])])
                if (routetable != -1):
                    print("routetable: %s" % routetable)
                    doc = self.setroutetablexml(routetable)
                    print("下发路由表到%s的%s" %(msg['src']['ip'], key))
                    h = httplib2.Http()
                    resp, content = h.request("http://[" + msg['src']['ip'] + "]:12345/device/" + key \
                                              + "/routetable", "POST", doc)
                    print "收到回复: %s" %content
                else:
                    print "生成路由表失败！"
                    return

        for key in self.WIAPAobject[int(msg['dst']['panid'])].deviceinfo:
            if (self.WIAPAobject[int(msg['dst']['panid'])].deviceinfo[key] == '2'):
                routetable = self.createRoutetable(key, self.WIAPAobject[int(msg['dst']['panid'])])
                if (routetable != -1):
                    print("routetable: %s" % routetable)
                    doc = self.setroutetablexml(routetable)
                    print("下发路由表到%s的%s" %(msg['dst']['ip'], key))
                    h = httplib2.Http()
                    resp, content = h.request("http://[" + msg['dst']['ip'] + "]:12345/device/" + key \
                                              + "/routetable", "POST", doc)
                    print "收到回复: %s" %content
                else:
                    print "生成路由表失败！"
                    return

        mappingtable_tmp = self.createMappingtable(self.schedulinginfo, self.WIAPAobject[int(msg['src']['panid'])], \
                                               self.WIAPAobject[int(msg['dst']['panid'])])
        if(mappingtable_tmp == -1):
            print "生成映射表失败！"
            return
        mappingtable = self.setmappingtablexml(mappingtable_tmp)
        print("下发映射表到%s" %msg['src']['ip'])
        h = httplib2.Http()
        resp, content = h.request("http://[" + msg['src']['ip'] + "]:12345/device/"\
                                  + "/mappingtable", "POST", mappingtable)
        print "收到回复: %s" % content
        print("下发映射表到%s" % msg['dst']['ip'])
        h = httplib2.Http()
        resp, content = h.request("http://[" + msg['dst']['ip'] + "]:12345/device/"\
                                  + "/mappingtable", "POST", mappingtable)
        print "收到回复: %s" % content
        event_WIAPA_Path_Calculation = ofp_event.EventWIAPAPathCalculation(msg)
        self.event_brick_2 = app_manager.lookup_service_brick('ofp_event')
        self.event_brick_2.send_event_to_observers(event_WIAPA_Path_Calculation, MAIN_DISPATCHER)
        return
    def setroutetablexml(self, managerList):  #构造路由表XML

        '''
                1构造路由表
                managerList=[命令，数目，[routeID，源地址，目的地址，下一跳地址]，
                [routeID，源地址，目的地址，下一跳地址],......]
        '''
        doc = xml.dom.minidom.Document()
        root = doc.createElement('routetable')  # 设置根节点的属性
        root.setAttribute('xmlns', 'cquptSDN:routetable')
        # 将根节点添加到文档对象中
        doc.appendChild(root)

        nodeManager = doc.createElement('num')
        nodeManager.appendChild(doc.createTextNode(str(managerList[1])))
        root.appendChild(nodeManager)

        for i in managerList[2:]:
            nodeManager = doc.createElement('route')
            nodeName = doc.createElement('ID')
            # 给叶子节点name设置一个文本节点，用于显示文本内容
            nodeName.appendChild(doc.createTextNode(str(i[0])))

            nodeAge = doc.createElement("src")
            nodeAge.appendChild(doc.createTextNode(str(i[1])))

            nodeSex = doc.createElement("dst")
            nodeSex.appendChild(doc.createTextNode(str(i[2])))

            nodenext = doc.createElement("next")
            nodenext.appendChild(doc.createTextNode(str(i[3])))
            # 将各叶子节点添加到父节点Manager中，
            # 最后将Manager添加到根节点Managers中
            nodeManager.appendChild(nodeName)
            nodeManager.appendChild(nodeAge)
            nodeManager.appendChild(nodeSex)
            nodeManager.appendChild(nodenext)
            root.appendChild(nodeManager)
      #开始写xml文档
      #fp = open('xc', 'w')
      #idoc.writexml(fp, indent='\t', addindent='\t', newl='\n', encoding="utf-8")
        return  doc.toprettyxml()
    def setmappingtablexml(self, managerList):
        '''
                映射表格式：[命令，映射表数量，[源地址，MAC地址，routeID，源短地址，目的短地址，目的地址，routeID，源短地址，目的短地址]，
                [源地址，MAC地址，routeID，源短地址，目的短地址，目的地址，routeID，源短地址，目的短地址]......]
                '''
        doc = xml.dom.minidom.Document()
        root = doc.createElement('mappingtable')  # 设置根节点的属性
        root.setAttribute('xmlns', 'cquptSDN:mappingtable')
        # 将根节点添加到文档对象中
        doc.appendChild(root)

        nodeManager = doc.createElement('num')
        nodeManager.appendChild(doc.createTextNode(str(managerList[1])))
        root.appendChild(nodeManager)

        for i in managerList[2:]:
            nodeManager = doc.createElement('mapping')
            nodeName = doc.createElement('src')
            nodeName2 = doc.createElement('dst')
            # 给叶子节点name设置一个文本节点，用于显示文本内容
            nodeip = doc.createElement('ip')
            nodeip.appendChild(doc.createTextNode(str(i[0])))
            nodemac = doc.createElement('macaddress')
            nodemac.appendChild(doc.createTextNode(i[1]))
            nodeAge = doc.createElement("routeID")
            nodeAge.appendChild(doc.createTextNode(str(i[2])))

            nodesrcshortaddr = doc.createElement("srcshortaddr")
            nodesrcshortaddr.appendChild(doc.createTextNode(str(i[3])))

            nodedstshortaddr = doc.createElement("dstshortaddr")
            nodedstshortaddr.appendChild(doc.createTextNode(str(i[4])))

            nodeip2 = doc.createElement("ip")
            nodeip2.appendChild(doc.createTextNode(str(i[5])))
            nodemac2 = doc.createElement("macaddress")
            nodemac2.appendChild(doc.createTextNode(i[6]))
            nodenext = doc.createElement("routeID")
            nodenext.appendChild(doc.createTextNode(str(i[7])))

            nodesrcshortaddr1 = doc.createElement("srcshortaddr")
            nodesrcshortaddr1.appendChild(doc.createTextNode(str(i[8])))

            nodedstshortaddr1 = doc.createElement("dstshortaddr")
            nodedstshortaddr1.appendChild(doc.createTextNode(str(i[9])))
            # 将各叶子节点添加到父节点Manager中，
            # 最后将Manager添加到根节点Managers中
            nodeName.appendChild(nodeip)
            nodeName.appendChild(nodemac)
            nodeName.appendChild(nodeAge)
            nodeName.appendChild(nodesrcshortaddr)
            nodeName.appendChild(nodedstshortaddr)
            nodeName2.appendChild(nodeip2)
            nodeName2.appendChild(nodemac2)
            nodeName2.appendChild(nodenext)
            nodeName2.appendChild(nodesrcshortaddr1)
            nodeName2.appendChild(nodedstshortaddr1)
            nodeManager.appendChild(nodeName)
            nodeManager.appendChild(nodeName2)

            root.appendChild(nodeManager)

            return doc.toprettyxml()
    def net_manager(self, value):
        data = ''
        if value[0] == 'gettopo':   
            data_1 = "GET /topology HTTP\n"
            data_2 = data_1 + "Accept:application/xml\n"
            data_3 = data_2 + "Authentication:\n"
            data  = data_3 + " Content-Length:0"
        elif value[0]  == 'getdeviceinfo':
            data_1 = "GET /device/address/info HTTP/1.1\n"
            data_2 = data_1 + "Accept:application/xml\n"
            data_3 = data_2 + "Authentication:\n"
            data   = data_3 + "Content-Length:0"
        elif value[0] == 'getdevicelist':
            data_1 ="GET /device/HTTP/1.1\n"
            data_2 = data_1 + "Accept:application/xml\n"
            data_3 = data_2 + "Authentication:\n"
            data   = data_3 + "Content-Length:0"
        elif value[0] == 'getdeviceUAO':
            data_1 = "GET /device/shortaddress/uao HHTP/1.1"
            data_2 = data_1 + "Accept:application/xml\n"
            data_3 = data_2 + "Authentication:\n"
            data   = data_3 + "Content-Length:0"
        elif value[0] == 'setroutetable':      
            doc = self.setroutetablexml(value)          
            data_1 = "PUT /device/shortaddress/routetable HTTP/1.1"
            data_2 = data_1 + "Accept:application/xml\n"
            data_3 = data_2 + "Authentication:\n"
            data_4 = data_3 + "Content-Length:\n" 
            data = data_4 + doc
        return data
    def net_connect(self, c,addr):
              #  print len(q.get(1))
        flag = 0
        stri = c.recv(1000)
        print "收到信息%s" %stri
        for key in self.panid:
            if(key == addr):
                flag = 1
                print "来自%s的系统管理器已经登记过了！" %addr[0]
        if(flag == 0):
            self.panid.append(addr[0])
            print "登记来自%s的系统管理器！" %addr[0]

    def analysis_topology(dom):

        deviceinfo = {}
        topologyinfo = {}

        table = dom.getElementsByTagName("topology")[0]
        namelist = table.getElementsByTagName("edge")

        for name in namelist:
            categorylist = name.getElementsByTagName("category")
            addresslist = name.getElementsByTagName("address")
            for i in range(2):
                category = categorylist[i]
                textNode = category.childNodes[0].nodeValue.replace('\t', '').replace('\n', '').replace(' ', '')
                address = addresslist[i]
                textNode1 = address.childNodes[0].nodeValue.replace('\t', '').replace('\n', '').replace(' ', '')
                deviceinfo[textNode1] = textNode

        for tmp in namelist:
            src = tmp.getElementsByTagName("src")
            dst = tmp.getElementsByTagName("dst")

            srcaddr = src[0].getElementsByTagName("address")
            dstaddr = dst[0].getElementsByTagName("address")

            srcaddress = srcaddr[0].childNodes[0].nodeValue.replace('\t', '').replace('\n', '').replace(' ', '')
            dstaddress = dstaddr[0].childNodes[0].nodeValue.replace('\t', '').replace('\n', '').replace(' ', '')

            topologyinfo[srcaddress] = dstaddress

        return deviceinfo, topologyinfo

    def TCPServer(self, q, req, Threadname): 
        s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        s.bind(('', 12344))
        s.listen(5)
        i = 0
        while True:       
            c,addr = s.accept()
            print strftime('%Y-%m-%d %H:%M:%S', localtime(time())) + "一个WIA-PA系统管理器连接到控制器"
            t3 = threading.Thread(target=self.net_connect,args=(c,addr))
            t3.start()
            sleep(1)
            i=i+1
#        self.queue_get = hub.spawn(self._queue_get)
#        self.TCP_server = hub.spawn(multhreading_new)
    def getWIAPAinformation(self, id, strcom):
        if strcom[0] == "gettopo":
            print "获取PANID为%d的WIA-PA网络的信息" %self.panid[0]
            self.q[self.panid[0] - 1].put(["gettopo"],1)
            self.topo.append(self.req[self.panid[0] - 1].get(1))
    def getMACaddress(self, host):
        os.popen('ping6 -c 1 %s' % host)
        os.popen('ip -6 neigh>text')
        # for line in sys.stdin:
        #    print line
        # grep with a space at the end of IP address to make sure you get a single line
        fields = os.popen('grep "%s " ./text' % host).read().split()
        if len(fields) >= 6 and fields[4] != "00:00:00:00:00:00":
            return fields[4]
        else:
            print 'no response from', host
            return -1
    def getWIAPAobject(self, msg):
        # commond = ['gettopo']
        # data = self.net_manager(commond)
        h = httplib2.Http()
        resp, content = h.request("http://[" + msg['ip'] + "]:12345/topology", "GET")
        print "PANID为%s的WIA-PA网络拓扑信息为%s" %(msg['panid'], content)
        dom = xml.dom.minidom.parseString(content)
        deviceinfo, topologyinfo = self.analysis_topology(dom)
        WIAPAnet = WIAPAnetwork(deviceinfo, topologyinfo, int(msg['panid']), msg['ip'])
        macaddr = self.getMACaddress(msg['ip'])
        if(macaddr == -1):
            print "IP为%s的WIA-PA网关MAC地址获取失败！" %msg['ip']
            return -1
        WIAPAnet.macaddress = macaddr
        WIAPAnet.shortest_path_creat(msg['shortaddr'])
        self.WIAPAobject.append(WIAPAnet)

    def createMappingtable(self, info, src, dst):
        '''
        函数名：createMappingtable
    输入参数：routeid对应信息
    输出参数：列表
    功能：生成映射表
    映射表格式：[命令，映射表数量，[源地址，MAC地址，routeID，源短地址，目的短地址，目的地址，routeID，源短地址，目的短地址]，
    [源地址，MAC地址，routeID，源短地址，目的短地址，目的地址，routeID，源短地址，目的短地址]......]
        '''
        mapping = []
        num = 0

        mapping.append("setmappingtable")
        mapping.append(num)

        for key in self.schedulinginfo:
            table = []
            table.append(key[0])
            table.append(key[1])
            table.append(key[2][0])

            for tmp in src.routeIDlist:
                if src.routeIDlist[tmp][0] == table[2]:
                    table.append(tmp[0])
                    table.append(tmp[-1])
                    break
            else:
                return -1
            table.append(self.schedulinginfo[key][0])
            table.append(self.schedulinginfo[key][1])
            table.append(self.schedulinginfo[key][2][1])
            for tmp in dst.routeIDlist:
                if dst.routeIDlist[tmp][1] == table[7]:
                    table.append(tmp[0])
                    table.append(tmp[-1])
                    break
            else:
                return -1

            mapping.append(table)
            num = num + 1

        mapping[1] = num

        return mapping

    def createRoutetable(self, shortaddr, network_n):
        '''
        :param shortaddr:
        :param network_n:
        :return: routetable
        创建路由表列表，添加命令名和数目。
        路径列表是一个包含所有路径的列表，双重循环搜索短地址，搜索到路径，查找routeID,填入路由表表项列表，
        查找源地址目的地址，填入路由表表项列表，查找下一跳地址，填入路由表表项列表，将路由表表项列表添加到路由表列表中，
        路由计数变量加1
        将路由计数变量填入路由表列表中。
        '''

        routetable = []
        path = []
        tablenum = 0
        routetable.append('setroutetable')
        routetable.append(0)

        path = network_n.pathlist
        for i in path:
            for k in i:
                if k == shortaddr:
                    table = []
                    routeID = network_n.get_routeID(i)
                    table.append(routeID[1])  # 下行路径
                    table.append(i[0])
                    table.append(i[-1])
                    num = i.index(k)
                    table.append(i[num + 1])
                    routetable.append(table)
                    tablenum = tablenum + 1

                    table_1 = []
                    table_1.append(routeID[0])  # 上行路径
                    table_1.append(i[-1])
                    table_1.append(i[0])
                    num = i.index(k)
                    table_1.append(i[num - 1])
                    routetable.append(table_1)
                    tablenum = tablenum + 1

        if (tablenum == 0):
            return -1
        routetable[1] = tablenum
        return routetable
class SimpleWIAPAController(ControllerBase):
    
    def __init__(self, req, link, data, **config):
        super(SimpleWIAPAController, self).__init__(req, link, data, **config)
        self.simple_WIAPA_app = data[simple_WIAPA_instance_name]

    @route('simpleWIAPA', url, methods=['PUT'])
    def put_mac_table(self, req, **kwargs):
        print "get a info"
        simple_switch = self.simple_WIAPA_app
        print "%s" %req.body
        new_entry = eval(req.body)
        print "%s" %new_entry['src']['ip']
        event_WIAPA_Command_In = ofp_event.EventWIAPACommandIn(new_entry)
        self.event_brick = app_manager.lookup_service_brick('ofp_event')
        self.event_brick.send_event_to_observers(event_WIAPA_Command_In, MAIN_DISPATCHER)
#        try:
            
#        body = json.dumps(new_entry)
#        print "%s" %body
#        return Response(content_type='application/json', body=body)
#        except Exception as e:
#            return Response(status=500)
#@set_ev_cls(ofp_event.EventWIAPAPathCalculation, MAIN_DISPATCHER)
#def Event_Test(self, ev):
#msg = ev.msg
#self.logger.info("%s" %msg)
