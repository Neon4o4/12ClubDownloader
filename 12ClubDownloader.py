# !/usr/bin/env python

# coding: utf8

"""
Used for downloading videos from 12club.nankai.edu.cn automatically.
An access to the campus network of NKU is required.
Dependency: PyQuery
"""


from re import match, search, findall
from contextlib import closing
from urllib2 import urlopen, unquote
from shutil import copyfileobj
from datetime import datetime
from os import mkdir, chdir, getcwd
from os.path import isdir
from os import _exit as exit
from threading import Thread, Lock
from Queue import Queue
import signal


class String():
    '''solve the problem countered about args when using threading'''
    def __init__(self, sMsg):
        self.sMsg = sMsg

    def __str__(self):
        return self.sMsg


class Downloader():
    '''Download videos from 12club.nankai.edu.cn'''
    sDomain = '12club.nankai.edu.cn'
    pDownloaderGlobalLock = Lock()
    pMaxThreadLock = Lock()
    pTaskRunningLock = Lock()
    lFailList = set()
    pFailLock = Lock()
    lSuccList = set()
    pSuccLock = Lock()

    def __init__(self, sItemPage, maxThread=3, dirName=None):
        # varify the domain to request and format it
        if Downloader.isFullURL(sItemPage):
            if Downloader.matchDomain(sItemPage):
                if match('http', sItemPage):
                    self.sItemPageURL = sItemPage
                else:
                    self.sItemPageURL = 'http://' + sItemPage
            else:
                print 'Domain not match.'
                exit(-1)
        elif match('[0-9]+$', sItemPage):
            self.sItemPageURL = ''.join((
                'http://' + Downloader.sDomain + '/programs/',
                sItemPage))
        else:
            self.sItemPageURL = ''.join((
                'http://' + Downloader.sDomain,
                '' if match('/', sItemPage) else '/',
                sItemPage))
        self.maxThread = min(3, maxThread)
        # if directory name is not given, use current time
        self.dirName = dirName if dirName else datetime.now().isoformat() + '.d'

    def start(self):
        # there should not be more than 1 downloader working at the same time
        Downloader.pDownloaderGlobalLock.acquire()
        # find out all download links on this page
        lLinks = Downloader.getDownloadLinks(self.sItemPageURL)
        totalCount = len(lLinks)
        # create the directory if not exsiting
        if not isdir(self.dirName):
            mkdir(self.dirName)
        # then get download links by requesting them
        # set a thread pool to trace them
        lThreadPool = []
        # first run some download task
        print 'Start downloading from ', self.sItemPageURL, ' ...'
        if not totalCount:
            print 'Nothing found. Check URL and try again.'
            print 'Terminated.'
            exit(-3)
        print '%d files in total.' % totalCount
        print 'Files written in:', getcwd() + '/' + self.dirName
        for i in range(min(self.maxThread, totalCount)):
            # print lLinks
            t = Thread(
                target=Downloader.downloadFromLink,
                args=(String(lLinks[i]), String(self.dirName)),
                name=str(i))
            lThreadPool.append(t)
            t.start()
        # add the rest of tasks to a queue
        rest = lLinks[self.maxThread:]
        lLinks = Queue(len(rest))
        for url in rest:
            lLinks.put(url)
        # then accquire a lock
        Downloader.pMaxThreadLock.acquire()
        while not lLinks.empty():
            link = lLinks.get()
            if Downloader.pMaxThreadLock.acquire():
                # add those who failed just now to the queue
                # and retry them later
                if Downloader.pFailLock.acquire() \
                        and Downloader.pSuccLock.acquire():
                    for url in Downloader.lFailList:
                        if url not in Downloader.lSuccList:
                            lLinks.put(url)
                    Downloader.pFailLock.release()
                    Downloader.pSuccLock.release()
                t = Thread(
                    target=Downloader.downloadFromLink,
                    args=(String(link), String(self.dirName)),
                    name=str(i))
                lThreadPool.append(t)
                t.start()

        # make sure all tasks have terminated and succeeded
        lThreadPool = [thrd for thrd in lThreadPool if thrd.is_alive()]
        while lThreadPool:
            for t in lThreadPool:
                t.join(0.5)
            lThreadPool = [thrd for thrd in lThreadPool if thrd.is_alive()]

        if Downloader.lFailList:
            print
            print '%d succeeded,' % len(Downloader.lSuccList),
            print '%d failed' % len(Downloader.lFailList)
            print 'Retrying failures...'
            while Downloader.lFailList:
                for url in list(Downloader.lFailList):
                    Downloader.downloadFromLink(url, self.dirName)
        # finished
        Downloader.pDownloaderGlobalLock.release()
        if Downloader.pMaxThreadLock.locked():
            Downloader.pMaxThreadLock.release()
        print 'All download tasks finished.'
        print totalCount, ' files stored in directory ', self.dirName

    @classmethod
    def downloadFromLink(cls, url, dirName):
        url = str(url)
        dirName = str(dirName)
        try:
            with closing(urlopen('http://' + Downloader.sDomain + url)) as r:
                filename = Downloader.getFilename(r.url)
                print 'Downloading: %s ...' % filename
                with open(dirName + '/' + filename, 'wb') as f:
                    copyfileobj(r, f)
        # trace failure
        except:
            print 'Failed: %s retry later...' % url
            if Downloader.pFailLock.acquire():
                Downloader.lFailList.add(url)
                Downloader.pFailLock.release()
            return
        # successed. remove from failure list if exist and add to succeed list
        if Downloader.pFailLock.acquire() and Downloader.pSuccLock.acquire():
            if url in Downloader.lFailList:
                Downloader.lFailList.remove(url)
            Downloader.lSuccList.add(url)
            Downloader.pFailLock.release()
            Downloader.pSuccLock.release()
        # task finished. now main thread can continue to run tasks
        if Downloader.pMaxThreadLock.locked():
            Downloader.pMaxThreadLock.release()
        print 'Finished: ', filename

    @classmethod
    def matchDomain(cls, url):
        return (
            search('^' + Downloader.sDomain, url)
            or
            search('^http://' + Downloader.sDomain, url)
        )

    @classmethod
    def isFullURL(cls, url):
        return (
            match(Downloader.sDomain + '/programs/[0-9]+', url)
            or
            match('http://' + Downloader.sDomain + '/programs/[0-9]+', url)
        )

    @classmethod
    def getDownloadLinks(cls, sItemPageURL):
        from pyquery import PyQuery as pq
        pItemPage = pq(url=sItemPageURL)
        lLinks = pItemPage('a').filter('.download_link')
        return [tag.get('href') for tag in lLinks]

    @classmethod
    def getFilename(cls, ftpURL):
        # find out the last part
        filename = findall('/([^/]+)$', ftpURL)[0]
        return unquote(filename).decode('utf8')


def signal_handler(sig, frame):
    print
    print 'Signal received:', sig
    print 'Terminated.'
    exit(1)


def main(link='/programs/1218', dirName='12ClubDownload'):
    # link = 'http://12club.nankai.edu.cn/programs/1116'
    signal.signal(signal.SIGINT, signal_handler)
    import sys
    chdir(sys.path[0])
    if not dirName:
        dirName = '12ClubDownload'
    Downloader(dirName=dirName, sItemPage=link).start()

if __name__ == '__main__':
    print '=============== Welcome to 12Club Downloader ==============='
    print 'It will help you to download files from 12club.nankai.edu.cn'
    print 'Make sure you have an access to the website'
    print 'as well as the writing permission of local directory'
    print '============================================================'
    print 'Enter the homepage\'s link address of anime you want to download:'
    print 'It should be something like:',
    print 'http://12club.nankai.edu.cn/programs/1218 or 1218'
    link = raw_input('Input: ')
    if not link:
        print 'Invalid URL. Terminated.'
        exit(-2)
    dirName = raw_input('Where to store the file downloaded: ')
    if not dirName:
        print 'No directory name detected. Default directory will be used.'
        dirName = None
    main(link, dirName)
