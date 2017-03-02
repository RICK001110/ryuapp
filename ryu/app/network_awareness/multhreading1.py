# -*- coding:utf-8 -*-
import socket
import threading
from time import ctime,sleep
from Queue import Queue


import xml.dom.minidom
def setroutetablexml(managerList):  #构造路由表XML

    doc = xml.dom.minidom.Document()
    root = doc.createElement('routetable')  #设置根节点的属性
    root.setAttribute('xmlns', 'cquptSDN:routetable')   
    #将根节点添加到文档对象中
    doc.appendChild(root)
   
    nodeManager = doc.createElement('num')
    nodeManager.appendChild(doc.createTextNode('name'))
    root.appendChild(nodeManager)

    for i in managerList[1:]:
        a=i.keys()
        nodeManager = doc.createElement('route')
        nodeName = doc.createElement('ID')
        #给叶子节点name设置一个文本节点，用于显示文本内容
        nodeName.appendChild(doc.createTextNode(str(i['ID'])))
  
        nodeAge = doc.createElement("src")
        nodeAge.appendChild(doc.createTextNode(str(i["src"])))
  
        nodeSex = doc.createElement("dst")
        nodeSex.appendChild(doc.createTextNode(str(i["dst"])))
       #将各叶子节点添加到父节点Manager中，
       #最后将Manager添加到根节点Managers中
        nodeManager.appendChild(nodeName)
        nodeManager.appendChild(nodeAge)
        nodeManager.appendChild(nodeSex)
        root.appendChild(nodeManager)
      #开始写xml文档
      #fp = open('xc', 'w')
      #idoc.writexml(fp, indent='\t', addindent='\t', newl='\n', encoding="utf-8")
    return  doc.toprettyxml()


def net_manager(value):
    data = ''
    if value[0] == 'gettopo':   
        data_1 = "GET /network-topology HTTP\n"
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
        doc = setroutetablexml(value)          
        data_1 = "PUT /device/shortaddress/routetable HTTP/1.1"
        data_2 = data_1 + "Accept:application/xml\n"
        data_3 = data_2 + "Authentication:\n"
        data_4 = data_3 + "Content-Length:\n" 
        data = data_4 + doc
    return data

def net_connect(c,q):
    while True:
        data=net_manager(q.get(1))
        if len(data) > 0: 
            c.sendall(data)
            data = ''

def TCPServer(q,Threadname): 
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 8056))
    s.listen(5)
    i = 0
    print "%s" %q
    while True:       
        c,addr = s.accept()
        t3 = threading.Thread(target=net_connect,args=(c,q[i]))
        t3.start()
        sleep(1)
        i=i+1





#主线程
            
#q = [Queue(100),Queue(100),Queue(100)]     #commandlist
#managerList = ["gettopo",{'ID' : '1',  'src' : '27.23.3', 'dst' : '27.54.4'}, 
#               {'ID' : '3', 'src' :  '30.23.5', 'dst' : '30.43.5'},
#               {'ID' : '4', 'src' : '29.23.5', 'dst' : '29.34.6'}]
#t1 = threading.Thread(target = TCPServer,args=(q,1))
#t1.setDaemon(True)         #守护线程     
#t1.start()                      
#sleep(1)
#q[0].put(managerList,1)        
#print 'wen'
#sleep(100)













        





       











