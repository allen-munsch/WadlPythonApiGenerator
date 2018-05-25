# WadlApiGenerator  Copyright (C) 2012  Aaron Greene
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import urllib2
import base64
import time
import sys
import re
import Log
from xml.dom.minidom import parseString, Document
from datetime import datetime
from xml.dom.minidom import parse, parseString


handler=urllib2.HTTPSHandler(debuglevel=1)
opener = urllib2.build_opener(handler)
urllib2.install_opener(opener)

def GetHttpContent(url, username=None, password=None):
    request = urllib2.Request(url)
    base64string = base64.encodestring(
        '{0}:{1}'.format(username, password)).replace('\n', '')
    request.add_header('Authorization', 'Basic %s' % base64string)
    return urllib2.urlopen(request).read()


class HttpConnection:
    def __init__(self):
        self.CallLogPath = 'CallLog.txt'
        self.Username = ''
        self.Password = ''
        self.Url = ''
        self.RequestType = ''
        self.Data = ''
        self.ContentType = ''
        self.Log = True
        self.ReturnError = False

    def Send(self):

        #
        # Configure connection header.
        #

        opener = urllib2.build_opener(urllib2.HTTPHandler)
        request = urllib2.Request(self.Url, data=self.Data)
        base64string = base64.encodestring('{0}:{1}'.format(
            self.Username, self.Password)).replace('\n', '')
        request.add_header('Authorization', 'Basic %s' % base64string)
        request.add_header('Content-Type', self.ContentType)
        request.add_header('Accept', self.ContentType)
        request.get_method = lambda: self.RequestType.upper()

        #
        # Attempt to send.
        #

        result = None
        try:

            #
            # Execute HTTP request and record time.
            #

            startTime = datetime.now()
            result = opener.open(request)
            runtime = (datetime.now() - startTime)
            result = result.read()

            #
            # Write execute time and other information to log file.
            #

            if self.Log:
                with open(self.CallLogPath, 'a') as file:
                    file.write('URL: {0}\nUSER: {8}\nPW: {9}\nTYPE: {6}\nBYTES SENT: {1}\nBYTES RECEIVED: {2}\nDATASENT: {4}\nRESPONSE: {5}\nRUNTIME: {3}\nTIME: {7}\n\n'
                               .format(self.Url, len(str(self.Data)) * 4, len(result) * 4, runtime, str(self.Data), result, self.RequestType, datetime.now(), self.Username, self.Password))

        #
        # Capture error.
        #

        except urllib2.URLError as e:
            if self.ReturnError:
                return str(e) + ' - ERROR!'
            with open(self.CallLogPath, 'a') as file:
                file.write('URL: {0}\nUSER: {4}\nPW: {5}\nTYPE: {2}\nDATASENT: {1}\nTIME: {3}\n\n'
                           .format(self.Url, str(self.Data), self.RequestType, datetime.now(), self.Username, self.Password))
            Log.Error('REST API ERROR: {0}\n{1}'.format(e, self.Url))
        return result


class WadlManager:

    def __init__(self, wadlUrl, username=None, password=None):

        #
        # Declare public objects.
        #
        self.username = username
        self.password = password
        self.cached = GetHttpContent(wadlUrl, username=username, password=password)
        self.Url = wadlUrl
        self.set = []
        self.Resources = {}
        self.Objects = {}

        #
        # Process WADL XML content.
        #
        dom = parseString(self.cached)
        self.__ProcessWadlXml(dom, None, None, None)
        self.__CombineObjectAttributes()

    #
    # Define recursive helper function for combining parent/child attributes.
    #

    def __CombineObjectAttributesHelp(self, base2):
        attributes = list(self.Objects.get(base2, {'attributes': []})['attributes'])
        for base3 in self.Objects.get(base2, {'bases': []})['bases']:
            attributes += list(self.__CombineObjectAttributesHelp(base3))
        return attributes

    #
    # Define initial function for combining parent/child attributes.
    #

    def __CombineObjectAttributes(self):
        for objectA in self.Objects:
            for base1 in self.Objects[objectA]['bases']:
                okay = list(self.__CombineObjectAttributesHelp(base1))
                self.Objects[objectA]['attributes'] += okay

    #
    # Define function for processing WADL grammar pages.
    #

    def __ProcessGrammerXml(self, node, complexType):
        if (node == None):
            return

        #
        # Capture initial complexType node.
        #
        if (node.nodeName == 'xs:complexType'):
            complexType = node.getAttributeNode('name').nodeValue
            self.Objects[complexType] = {}
            self.Objects[complexType]['attributes'] = []
            self.Objects[complexType]['bases'] = []
            self.Objects[complexType]['elements'] = []
        elif not complexType is None:
            #
            # Capture attribute node.
            #

            if (node.nodeName == 'xs:attribute'):
                self.Objects[complexType]['attributes'].append(
                    node.getAttributeNode('name').nodeValue)

            #
            # Capture extension object (inherited object).
            #

            elif (node.nodeName == 'xs:extension'):
                baseName = node.getAttributeNode('base').nodeValue
                baseName = re.sub('tns\:', '', baseName)
                self.Objects[complexType]['bases'].append(baseName)

            #
            # Capture element object.
            #

            elif (node.nodeName == 'xs:element'):
                nameNode = node.getAttributeNode('name')
                if not (nameNode == None):
                    self.Objects[complexType]['elements'].append(
                        nameNode.nodeValue)

        #
        # Continue to process child nodes recursively.
        #

        for childNode in node.childNodes:
            self.__ProcessGrammerXml(childNode, complexType)

    def __ProcessWadlXml(self, node, parent, currentUrl, currentApiName):
        if (node == None):
            return

        #
        # Capture include node, which will contain object definitions.
        #
        if (node.nodeName == 'grammars'):
            self.__ProcessGrammerXml(node, None)

        #
        # Capture resources node, which will contain the base URL.
        #

        elif (node.nodeName == 'resources'):
            self.base = currentUrl = re.sub(
                '/\Z', '', node.getAttributeNode('base').nodeValue)

        #
        # Capture resource node, which will contain a base API object.
        #

        elif (node.nodeName == 'resource'):
            currentUrl += node.getAttributeNode('path').nodeValue

        #
        # Capture method node, which will be a API call for the current parent.
        #

        elif (node.nodeName == 'method'):
            requestType = node.getAttributeNode('name').nodeValue
            currentApiName = re.sub('(\A/)|(/\Z)', '', currentUrl.replace(self.base, ''))
            currentApiName = '{0}_{1}'.format(re.sub('/', '_', currentApiName), requestType)
            self.Resources[currentApiName] = {}
            self.Resources[currentApiName]['requesttype'] = requestType
            self.Resources[currentApiName]['url'] = currentUrl
            self.Resources[currentApiName]['params'] = self.Resources[currentApiName].get('params', {})

            #
            # While in "method" goto parent and extract param nodes
            #

            for param_node in node.parentNode.getElementsByTagName('param'):
                name, style, typeA = None, None, None
                name = param_node.getAttributeNode('name').nodeValue
                if param_node.getAttributeNode('style'):
                    style = param_node.getAttributeNode('style').nodeValue
                if param_node.getAttributeNode('type'):
                    typeA = param_node.getAttributeNode('type').nodeValue
                self.Resources[currentApiName]['params'][name] = {'type': str(typeA), 'style': str(style)}


        #
        # Capture XML response and request node, will be the request (object) type and response type of current APL call.
        #

        elif (node.nodeName == 'ns2:representation'):
            if (node.getAttributeNode('mediaType').nodeValue == 'application/xml'):
                if (parent.nodeName == 'request'):
                    self.Resources[currentApiName]['xmlrequest'] = node.getAttributeNode(
                        'element').nodeValue
                else:
                    self.Resources[currentApiName]['xmlresponse'] = node.getAttributeNode(
                        'element').nodeValue

        #
        # Capture URL parameter node, will be a parameter for the URL.
        #
        if (node.nodeName == 'param'):
            pass
        #
        # Continue to process child nodes recursively.
        #

        for childNode in node.childNodes:
            self.__ProcessWadlXml(childNode, node, currentUrl, currentApiName)

    def GetConnection(self, username, password, returnError=False):
        innerSelf = self

        #
        # Define decorator fuction which is used to force the "resource" parameter into API calls.
        #

        def createFuction(resource):
            def wrap(function):
                def wrapped(* args, ** kwargs):
                    return function(args, kwargs, resource)
                return wrapped
            return wrap

        #
        # Define connection class using META programming.
        #

        class Connection:
            def __init__(self):
                self.Apis = {}
                self.username = username
                self.password = password
                self.ReturnError = returnError
                for resource in innerSelf.Resources:

                    #
                    # Define API fuction.
                    #

                    @createFuction(resource)
                    def api(args, kwargs, resource):

                        #
                        # Create connection object.
                        #

                        connection = HttpConnection()
                        connection.Username = self.username
                        connection.Password = self.password
                        connection.ContentType = 'application/xml'
                        connection.RequestType = innerSelf.Resources[resource]['requesttype']
                        connection.ReturnError = self.ReturnError
                        connection.Url = innerSelf.Resources[resource]['url']

                        #
                        # Check and set connection.
                        #

                        firstUrlArg = True
                        requestXmlObject = None if not 'xmlrequest' in innerSelf.Resources[
                            resource] else innerSelf.Resources[resource]['xmlrequest']
                        xmlElements = ''
                        xmlAttributes = ''
                        for argument in kwargs:
                            #
                            # Check if argument is URL parameter.
                            #
                            if argument in innerSelf.Resources[resource]['params']:
                                firstChar = '?' if firstUrlArg else '&'
                                connection.Url = connection.Url.format(**kwargs)
                                # connection.Url += '{0}{1}={2}'.format(firstChar, argument, kwargs[argument])
                                firstUrlArg = False
                                continue

                            #
                            # Check if argument is XML parameter.
                            #

                            if not (requestXmlObject is None):
                                if argument in innerSelf.Objects[requestXmlObject]['attributes']:
                                    xmlAttributes += ' {0}="{1}"'.format(
                                        argument, kwargs[argument])
                                    continue
                                if argument in innerSelf.Objects[requestXmlObject]['elements']:
                                    xmlElements += '<{0}>{1}</{0}>'.format(
                                        argument, kwargs[argument])
                                    continue
                            #
                            # At this point throw error because given parameter was not found.
                            #

                            Log.Error('Invalid API argument API: {0}, Argument {1}={2}'.format(
                                resource, argument, kwargs[argument]))

                        #
                        # Append XML meta data if any XML parameters were added.
                        #

                        if not requestXmlObject is None:
                            connection.Data = '<?xml version="1.0" ?><{0}{1}>{2}</{0}>'.format(
                                requestXmlObject, xmlAttributes, xmlElements)

                        #
                        # Send request.
                        #

                        return connection.Send()

                    #
                    # Set function call and information.
                    #

                    self.__dict__[resource] = api
                    self.Apis[resource] = api
        return Connection()
