# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

import sys
import fitz
import json
import tempfile
import numpy as np
from copy import deepcopy
from PyQt5.uic import loadUi
from PyQt5.QtWidgets import QApplication, QMainWindow, QFileDialog, QPushButton, QTableWidgetItem
from PyQt5.QtCore import pyqtSignal
from pydicom.dataset import FileMetaDataset, FileDataset, Dataset
from pydicom.uid import generate_uid, PYDICOM_IMPLEMENTATION_UID
from pynetdicom.sop_class import Verification, PatientRootQueryRetrieveInformationModelFind, MultiFrameGrayscaleByteSecondaryCaptureImageStorage
from pynetdicom import AE
import datetime


def check_umlaute(dq):
    name = dq.PatientName.components[0]
    dqs = [dq]
    if "AE" in name or "OE" in name or "UE" in name:
        name = name.replace("AE", "Ä")
        name = name.replace("OE", "Ö")
        name = name.replace("UE", "Ü")
        dq2 = deepcopy(dq)
        dq2.PatientName = name
        dqs.append(dq2)
    elif "Ä" in name or "Ö" in name or "Ü" in name:
        name = name.replace("Ä", "AE")
        name = name.replace("Ö", "OE")
        name = name.replace("Ü", "UE")
        dq2 = deepcopy(dq)
        dq2.PatientName = name
        dqs.append(dq2)
    return dqs


class dropArea(QPushButton):
    
    pathChanged = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.clicked.connect(self.click)
        self.path = ""
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.path = event.mimeData().urls()[0].toLocalFile()
            self.setText(self.path.split('/')[-1])
            self.pathChanged.emit()
            event.accept()
        else:
            event.ignore()
    
    def click(self):
        dialog_path = QFileDialog.getOpenFileName(self,"PDF laden ...", "", "*.pdf")[0]
        if dialog_path == '':
            return
        self.path = dialog_path
        self.setText(self.path.split('/')[-1])
        self.pathChanged.emit()


class mainWindow(QMainWindow):

    def __init__(self):  
        super().__init__()
        loadUi("pdf2pacs.ui", self)
        with open("einstellungen.txt", "r") as fp: self.prob = json.load(fp)
        try:
            ae = AE(self.prob["SCP AE"])
            ae.add_supported_context(Verification)
            ae.start_server(("127.0.0.1", self.prob["SCP Port"]), block=False)
            self.statusBar.showMessage("Der SCP Server wurde erfolgreich gestartet.")
        except Exception as e:
            self.statusBar.showMessage("Der SCP Server wurde nicht gestartet: "+str(e))
        self.centralWidget().setContentsMargins(9, 9, 9, 9)
        self.buttonLoadPDF.pathChanged.connect(self.loadPDF)
        self.buttonSearchPACS.clicked.connect(self.searchPACS)
        self.buttonSendPACS.clicked.connect(self.sendPACS)
        self.studienbeschreibung.setText(self.prob["Standard Studienbeschreibung"])
        self.serienbeschreibung.setText(self.prob["Standard Serienbeschreibung"])
        self.studies = []

    def loadPDF(self):
        try:
            text = self.buttonLoadPDF.text()[:-4].split('__')
            patient = text[0].split('_')
            aufnahmezeit = text[2].replace('_','.',2).replace('_',' ',1).replace('_',':',2)
            self.nachname.setText(patient[0])
            self.vorname.setText(patient[-1])
            self.aufnahmezeit.setText(aufnahmezeit)
            self.studiendatum.setText(aufnahmezeit[:10])
            self.searchPACS()
        except:
            self.statusBar.showMessage("PDF Datei nicht richtig benannt")
            self.table.setRowCount(0)
            self.buttonLoadPDF.setText("PDF Datei laden ...")
            self.nachname.clear()
            self.vorname.clear()
            self.studiendatum.clear()
            self.aufnahmezeit.clear() 
    
    def searchPACS(self):
        dq = Dataset()
        dq.QueryRetrieveLevel = 'STUDY'
        dq.PatientName = "*"+self.nachname.text().upper()+'*^*'+self.vorname.text().upper()+"*"
        if dq.PatientName == '**^**':
            self.statusBar.showMessage("Patientenname fehlt")
            return
        dq.PatientID = ''
        dq.PatientBirthDate = ''
        dq.PatientSex = ''
        dq.StudyDescription = self.studienbeschreibung.text()
        datum = self.studiendatum.text()
        dq.StudyDate = datum[6:10]+datum[3:5]+datum[:2]
        dq.StudyTime = ''
        dq.StudyInstanceUID = ''
        dq.StudyID = ''
        dq.AccessionNumber = ''
        dqs = check_umlaute(dq)
        self.table.setRowCount(0)
        self.statusBar.showMessage("Verbindung wird aufgebaut ...")
        ae = AE(self.prob["C-FIND calling AE"])
        ae.add_requested_context(PatientRootQueryRetrieveInformationModelFind)
        ae.connection_timeout = self.prob["Verbindungsabbruch"]
        assoc = ae.associate(self.prob["C-FIND called IP"],
                             self.prob["C-FIND called Port"],
                             ae_title=self.prob["C-FIND called AE"])
        if assoc.is_established:
            self.studies = []
            for dq in dqs:
                responses = assoc.send_c_find(dq, PatientRootQueryRetrieveInformationModelFind)
                for (status, identifier) in responses:
                    if status:
                        self.statusBar.showMessage("C-FIND Query Status: 0x{0:04X}".format(status.Status))
                    else:
                        self.statusBar.showMessage("Zeitüberschreitung, Abbruch der Verbindung oder ungültige Antwort")
                    if type(identifier) is Dataset:
                        self.studies.append(identifier)
                        row = self.table.rowCount()
                        self.table.insertRow(row)
                        self.table.setItem(row, 0, QTableWidgetItem(identifier.PatientName.family_name))
                        self.table.setItem(row, 1, QTableWidgetItem(identifier.PatientName.given_name))
                        self.table.setItem(row, 2, QTableWidgetItem(identifier.PatientID))
                        datum = identifier.StudyDate
                        self.table.setItem(row, 3, QTableWidgetItem(datum[6:8]+'.'+datum[4:6]+'.'+datum[:4]))
                        self.table.setItem(row, 4, QTableWidgetItem(identifier.StudyDescription))
            assoc.release()
            if self.statusBar.currentMessage() == "C-FIND Query Status: 0x0000":
                self.statusBar.showMessage("Anzahl an gefundenen Studien: {0}".format(len(self.studies)))
            self.table.selectRow(0)
        else:
            self.statusBar.showMessage("Verbindung abgelehnt, abgebrochen oder nie verbunden")
    
    def sendPACS(self):
        row = self.table.currentRow()
        if row == -1:
            self.statusBar.showMessage("Keine Studie als Sendeziel ausgewählt")
            return
        file_meta = FileMetaDataset()
        file_meta.FileMetaInformationVersion = b"\x00\x01"
        file_meta.TransferSyntaxUID = "1.2.840.10008.1.2.1"  # Explicit VR Little Endian
        file_meta.MediaStorageSOPClassUID = MultiFrameGrayscaleByteSecondaryCaptureImageStorage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.ImplementationClassUID = PYDICOM_IMPLEMENTATION_UID
        file_meta.ImplementationVersionName = "pdf2dcm1.0"

        filename = tempfile.NamedTemporaryFile().name
        ds = FileDataset(filename, {}, file_meta=deepcopy(file_meta), preamble=b"\0" * 128)
        ds.is_little_endian = True
        ds.is_implicit_VR = False

        ds.SpecificCharacterSet = "ISO_IR 192"
        ds.ImageType = "DERIVED,SECONDARY"
        ds.Modality = "OT"  # document
        ds.ConversionType = "WSD"  # workstation
        ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        
        dt = datetime.datetime.now()
        ds.InstanceCreationDate = dt.strftime("%Y%m%d")
        ds.InstanceCreationTime = dt.strftime("%H%M%S.%f")
        ds.ContentDate = dt.strftime("%Y%m%d")
        ds.ContentTime = dt.strftime("%H%M%S.%f")
        zeit = self.aufnahmezeit.text()
        ds.SeriesDate = zeit[6:10]+zeit[3:5]+zeit[:2]
        ds.SeriesTime = zeit[11:13]+zeit[14:16]+zeit[17:19]
        ds.AcquisitionDate = zeit[6:10]+zeit[3:5]+zeit[:2]
        ds.AcquisitionTime = zeit[11:13]+zeit[14:16]+zeit[17:19]

        dq = self.studies[row]
        ds.PatientName = dq.PatientName
        ds.PatientID = dq.PatientID
        ds.PatientBirthDate = dq.PatientBirthDate
        ds.PatientSex = dq.PatientSex
        ds.StudyDate = dq.StudyDate
        ds.StudyTime = dq.StudyTime
        ds.StudyDescription = dq.StudyDescription
        ds.StudyInstanceUID = dq.StudyInstanceUID
        ds.StudyID = dq.StudyID
        ds.AccessionNumber = dq.AccessionNumber

        ds.SeriesDescription = self.serienbeschreibung.text()
        ds.SeriesInstanceUID = generate_uid()
        ds.SeriesNumber = "1"
        ds.InstanceNumber = 1
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.PlanarConfiguration = 0
        
        doc = fitz.open(self.buttonLoadPDF.path)
        pixmap = []
        for page in doc:
            pix = page.get_pixmap(colorspace=fitz.csGRAY, dpi=150)
            pixmap.append(np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width)))
        pixmap = np.array(pixmap)
        
        shape = np.shape(pixmap)
        ds.NumberOfFrames = shape[0]
        ds.Rows = shape[1]
        ds.Columns = shape[2]
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.LargestImagePixelValue = 255
        ds.SmallestImagePixelValue = 0
        ds.PixelData = pixmap.tobytes()

        ds.fix_meta_info()

        self.statusBar.showMessage("Verbindung wird aufgebaut ...")
        ae = AE(self.prob["C-STORE calling AE"])
        ae.add_requested_context(MultiFrameGrayscaleByteSecondaryCaptureImageStorage)
        ae.connection_timeout = self.prob["Verbindungsabbruch"]
        assoc = ae.associate(self.prob["C-STORE called IP"],
                             self.prob["C-STORE called Port"],
                             ae_title=self.prob["C-STORE called AE"])
        if assoc.is_established:
            status = assoc.send_c_store(ds)
            self.statusBar.showMessage("C-MOVE query status: 0x{0:04x}".format(status.Status))
            assoc.release()
            if self.statusBar.currentMessage() == "C-MOVE query status: 0x0000":
                datum = ds.StudyDate
                datum = datum[6:8]+'.'+datum[4:6]+'.'+datum[:4]
                self.statusBar.showMessage(r'Serie "{0}" erfolgreich gesendet an: {1} - {2} ({3})'.format(ds.SeriesDescription, ds.PatientName, ds.StudyDescription, datum))
                self.table.setRowCount(0)
                self.buttonLoadPDF.setText("PDF Datei laden ...")
                self.nachname.clear()
                self.vorname.clear()
                self.studiendatum.clear()
                self.aufnahmezeit.clear()
        else:
            self.statusBar.showMessage("Verbindung abgelehnt, abgebrochen oder nie verbunden")


if __name__ == "__main__":
    app = QApplication(sys.argv)              # Applikationsobjekt erzeugen
    ui = mainWindow()                         # Instanz anlegen
    ui.show()                                 # Widget anzeigen
    sys.exit(app.exec())                      # Hauptschleife


