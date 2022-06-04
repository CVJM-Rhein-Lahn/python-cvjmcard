#!/usr/bin/env python3
from xml.dom.minidom import parseString
from lxml import etree
from bs4 import BeautifulSoup
import requests
import sys
import csv

LOGIN_URL = 'https://cvjm-card.de/cvjm-card/cgi/verein/verein.pl'

def getTextOfNode(node):
	txt = ''
	if node.nodeType != 3:
		if node.hasChildNodes():
			for subNode in node.childNodes:
				txt += getTextOfNode(subNode)
	else:
		txt += node.wholeText
	return txt.strip()

class Statistic(object):

	def __init__(self):
		self._counts = {}

	def addNumber(self, key, memberType, gender, nr):
		if key not in self._counts.keys():
			self._counts[key] = {
				'Mitglieder': {'männl.': 0, 'weibl.': 0},
				'Gäste (1)': {'männl.': 0, 'weibl.': 0},
				'Mitarbeiter': {'männl.': 0, 'weibl.': 0}
			}
		self._counts[key][memberType][gender] += nr

	def getTotal(self):
		total = 0
		for c in self._counts.values():
			for m in c.values():
				total += sum(m.values())
		return total

	def getTotalPaying(self):
		total = 0
		for cAgeKey, c in self._counts.items():
			if cAgeKey not in ['bis 8 Jahre', '9 - 13 Jahre']:
				for mTypeKey, m in c.items():
					if mTypeKey == 'Mitglieder':
						total += sum(m.values())
		return total

	def getTotalPayingKV(self):
		total = 0
		if cAgeKey not in ['bis 8 Jahre']:
			for cAgeKey, c in self._counts.items():
				for mTypeKey, m in c.items():
					if mTypeKey == 'Mitglieder':
						total += sum(m.values())
		return total

	def getTotalGuests(self):
		total = 0
		for cAgeKey, c in self._counts.items():
			for mTypeKey, m in c.items():
				if mTypeKey == 'Gäste (1)':
					total += sum(m.values())
		return total

	def getTotalWorkers(self):
		total = 0
		for cAgeKey, c in self._counts.items():
			for mTypeKey, m in c.items():
				if mTypeKey == 'Mitarbeiter':
					total += sum(m.values())
		return total

class Address(object):

	def __init__(self, club, addressNo, function, description, name, addAddress, street, postCodeCity, phone, fax, mail):
		self.club = club
		self.addressNo = addressNo
		self.function = function
		self.description = description
		self.name = name
		self.addAddress = addAddress
		self.street = street
		self.postCodeCity = postCodeCity
		self.phone = phone
		self.fax = fax
		self.mail = mail
		self.zipCode = None
		self.city = None

		# try to split the postCodeCity into zipCode and city.
		if self.postCodeCity:
			self._parseZipCity()

	def _parseZipCity(self):
		zipCode, city = self.postCodeCity.lstrip().split(' ', 1)
		if zipCode and zipCode.isdigit() and city:
			self.zipCode = zipCode
			self.city = city

	def getName(self):
		firstName, lastName = self.name.strip().rsplit(' ', 1)
		return (firstName, lastName)

	def getFirstName(self):
		return self.getName()[0]

	def getLastName(self):
		return self.getName()[1]

	def getFormatted(self):
		firstName, lastName = self.name.strip().rsplit(' ', 1)
		return lastName + ', ' + firstName

class Club(object):
	
	def __init__(self, clubName, clubNo=None, clubContact=None, urlExport=None):
		self.clubNo = clubNo
		self.contactNo = clubContact
		self.name = clubName
		self.addresses = []
		self._urlExport = urlExport

	def parse(self):
		self.parseAddresses()

	def parseAddresses(self):
		if not self._urlExport:
			return None

		r = requests.get(self._urlExport)
		soup = BeautifulSoup(r.content, 'lxml')
		fixedHtml = soup.prettify()
		parser = etree.XMLParser(recover=False)
		dom = parseString(fixedHtml.encode('utf-8'))
		# there are exactly two links: 
		# (1) link to CSV
		# (2) link to close window
		csvFile = None
		for a in dom.getElementsByTagName('a'):
			if a.hasAttribute('href') and '.csv' in a.getAttribute('href'):
				csvFile = a.getAttribute('href')

		if not csvFile:
			return

		r = requests.get(csvFile)
		if not r.status_code == 200:
			raise Exception('Could not download CSV file from ' + csvFile)

		# skip first line.
		csvContent = r.content[r.content.index(b'\n') + 1:].decode('iso-8859-1').split('\n')
		csv.register_dialect('cvjm-card', delimiter=';', quoting=csv.QUOTE_NONNUMERIC, quotechar='"', lineterminator='\n')
		csvReader = csv.reader(csvContent, 'cvjm-card')
		for row in csvReader:
			if not row:
				continue
			club, addressNo, function, description, name, addAddress, street, postCodeCity, phone, fax, mail, lastCol = row
			ad = Address(club, addressNo, function, description, name, addAddress, street, postCodeCity, phone, fax, mail)
			self.addresses.append(ad)

class DistrictClub(Club):
	
	def __init__(self, clubName, clubNo, clubContact, urlStatistic, urlExport):
		super().__init__(clubName, clubNo, clubContact, urlExport)
		self._urlStatistic = urlStatistic

class MemberClub(Club):

	def __init__(self, nr, name, statisticDate, payingMembers, urlStatistic, urlExport):
		super().__init__(name, urlExport=urlExport)
		self.nr = nr
		self.statisticDate = statisticDate
		self.payingMembers = payingMembers
		self.statistic = Statistic()
		self._urlStatistic = urlStatistic

	def getRechnungsAdresse(self):
		adsWKAN = None
		adsVK = None
		for a in self.addresses:
			if a.function == 'VK':
				adsVK = a
			elif a.function == 'WKAN':
				adsWKAN = a

		if adsWKAN is not None:
			return adsWKAN
		else:
			return adsVK

	def getKassenwart(self):
		ads = None
		for a in self.addresses:
			if a.function == 'VK':
				ads = a

		return ads

	def parse(self):
		self.parseStatistic()
		self.parseAddresses()

	def parseStatistic(self):
		r = requests.get(self._urlStatistic)
		soup = BeautifulSoup(r.content, 'lxml')
		fixedHtml = soup.prettify()
		parser = etree.XMLParser(recover=False)
		dom = parseString(fixedHtml.encode('utf-8'))
		statisticTable = dom.getElementsByTagName('table')[1]

		i = 0
		for line in statisticTable.getElementsByTagName('tr'):
			i += 1
			if i <= 2:
				continue

			key, memberMale, memberFemale, guestMale, guestFemale, workerMale, workerFemale = line.getElementsByTagName('td')
			keyText = getTextOfNode(key)
			memberMale = getTextOfNode(memberMale)
			memberMale = int(memberMale) if memberMale else 0
			self.statistic.addNumber(keyText, 'Mitglieder', 'männl.', memberMale)
			memberFemale = getTextOfNode(memberFemale)
			memberFemale = int(memberFemale) if memberFemale else 0
			self.statistic.addNumber(keyText, 'Mitglieder', 'weibl.', memberFemale)
			guestMale = getTextOfNode(guestMale)
			guestMale = int(guestMale) if guestMale else 0
			self.statistic.addNumber(keyText, 'Gäste (1)', 'männl.', guestMale)
			guestFemale = getTextOfNode(guestFemale)
			guestFemale = int(guestFemale) if guestFemale else 0
			self.statistic.addNumber(keyText, 'Gäste (1)', 'weibl.', guestFemale)
			workerMale = getTextOfNode(workerMale)
			workerMale = int(workerMale) if workerMale else 0
			self.statistic.addNumber(keyText, 'Mitarbeiter', 'männl.', workerMale)
			workerFemale = getTextOfNode(workerFemale)
			workerFemale = int(workerFemale) if workerFemale else 0
			self.statistic.addNumber(keyText, 'Mitarbeiter', 'weibl.', workerFemale)

class WestbundParser(object):

	def __init__(self, loginUrl, user, pwd):
		self._loginUrl = loginUrl
		self._user = user
		self._pwd = pwd
		self._clubs = []
		self._kvClub = None

	def getDistrictMembers(self):
		if not self._kvClub:
			return []

		ads = []
		for a in self._kvClub.addresses:
			if a.function != 'KG':
				ads.append(a)

		return ads

	def getAllMembers(self):
		ads = []
		found = []
		for c in self._clubs:
			for a in c.addresses:
				if a.name not in found and a.function not in ['VA']:
					ads.append(a)
					found.append(a.name)
		
		return ads

	def getAllVorsitzende(self):
		ads = []
		found = []
		for c in self._clubs:
			for a in c.addresses:
				if a.function in ['VV', 'V2']:
					if a.name not in found:
						ads.append(a)
						found.append(a.name)

		return ads

	def getVorstaende(self):
		ads = []
		for c in self._clubs:
			for a in c.addresses:
				if a.function in ['VV', 'V2', 'VS', 'VK']:
					ads.append(a)

		return ads

	def getKreisvertreter(self):
		ads = []
		found = []
		for c in self._clubs:
			for a in c.addresses:
				if a.function in ['VV', 'KT']:
					if a.name not in found:
						ads.append(a)
						found.append(a.name)
		return ads

	def getJungscharLeiter(self):
		ads = []
		for c in self._clubs:
			for a in c.addresses:
				if a.function in ['MJ', 'GJ', 'JJ', 'IN', 'JF']:
					ads.append(a)

		return ads

	def _parseDistrictClub(self, kvTab):
		# get all lines of clubs.
		try:
			tdLine = kvTab.getElementsByTagName('td')[0]
		except:
			return None

		try:
			fontLine = tdLine.getElementsByTagName('font')[1]
		except:
			return None

		clubName = None
		clubNumbers = None
		clubNo = None
		clubContact = None
		i = 0
		for child in fontLine.childNodes:
			if child.nodeName in ['table', 'br']:
				continue

			nodeText = getTextOfNode(child)
			if not nodeText:
				continue

			i += 1
			if i == 2:
				clubName = nodeText.strip()
			elif i == 3:
				clubNumbers = nodeText.strip()

		if clubNumbers and len(clubNumbers.split(',')) == 2:
			vno, cno = clubNumbers[1:-1].split(',')
			anyText, clubNoText = vno.rsplit(': ', 1)
			if clubNoText and clubNoText.strip().isdigit():
				clubNo = clubNoText.strip()
			anyText, contactNoText = cno.rsplit(': ', 1)
			if contactNoText and contactNoText.strip().isdigit():
				clubContact = contactNoText.strip()

		# try to find the links
		lnkPrintForm = None
		lnkExportForm = None
		i = 0
		for linkNode in fontLine.getElementsByTagName('a'):
			if i == 2:
				lnkPrintForm = linkNode.getAttribute('href')
			if i == 3:
				lnkExportForm = linkNode.getAttribute('href')
			if i >= 3:
				break
			i += 1

		# create the clubs element
		self._kvClub = DistrictClub(clubName, clubNo, clubContact, lnkPrintForm, lnkExportForm)
		self._kvClub.parse()

	def _parseTableMemberClubs(self, clubsTab):
		# get all lines of clubs.
		i = 0
		for line in clubsTab.getElementsByTagName('tr'):
			i += 1
			if i == 1:
				# skip first line
				continue

			try:
				nr, club, statisticDate, payingMembers, allMembers, links = line.getElementsByTagName('td')
			except ValueError as e:
				sys.stderr.write('Could not extract club statistic due to error: {:s}\n'.format(str(e)))
				continue
			# get text out of node.
			nrText = getTextOfNode(nr)
			if not nrText:
				# skip sum line.
				continue

			clubText = getTextOfNode(club)
			statisticDateText = getTextOfNode(statisticDate)
			payingMembersText = getTextOfNode(payingMembers)
			# get the different links
			lnkPrintForm = None
			lnkExportForm = None
			for lnk in links.getElementsByTagName('a'):
				if lnk.hasAttribute('href'):
					href = lnk.getAttribute('href')
					if '&trap' in href:
						lnkPrintForm = href
					else:
						lnkExportForm = href
			linksText = getTextOfNode(links)
			cl = MemberClub(int(nrText), clubText, statisticDate, int(payingMembersText), lnkPrintForm, lnkExportForm)
			cl.parse()
			self._clubs.append(cl)

	def parse(self):
		r = requests.post(self._loginUrl, files=dict({'m': '101', 'n': self._user, 'p': self._pwd, 'd': 'vereinsdb'}))
		soup = BeautifulSoup(r.content, 'lxml')
		fixedHtml = soup.prettify()
		parser = etree.XMLParser(recover=False)
		dom = parseString(fixedHtml.encode('utf-8'))
		# there are multiple tables. As we fix automatically, all parts are
		# put within one table. Last table is footer. 
		# Second + third table contains the logged in clubs editing links.
		# Fourth table contains the address information of current logged in club.
		# Summary:
		# 3+4. table contains list of links.
		# 5. table contains information about the Kreisverband Rhein-Lahn.
		# 6. table contains the table with the allocated regional clubs.
		tabs = dom.getElementsByTagName('table')
		if len(tabs) > 6 or len(tabs) < 6:
			sys.stderr.write('Could not identity types of tables!\n')
			sys.exit(1)

		self._parseDistrictClub(tabs[0])
		self._parseTableMemberClubs(tabs[4])
		del(tabs)

if __name__ == '__main__':
	import getpass, os
	USER = input('Username: ')
	PWD = getpass.getpass('Password: ')
	print('='*10 + os.linesep)
	wp = WestbundParser(LOGIN_URL, USER, PWD)
	wp.parse()
	print('Vorstände:')
	for kv in wp.getVorstaende():
		if kv.mail:
			print(kv.mail)
	print('\n')
	print('Kreisvertreter:')
	for kv in wp.getKreisvertreter():
		if kv.mail:
			print('"{:s} ({:s} von {:s})" <{:s}>'.format(kv.name, kv.function, kv.club, kv.mail))
		else:
			print('{:s} does not have E-Mail!'.format(kv.name))
	print('\n')
	print('Jungscharleiter:')
	for kv in wp.getJungscharLeiter():
		if kv.mail:
			print(kv.mail)
	print('\n')
	print('OV Vorsitzende:')
	for kv in wp.getAllVorsitzende():
		if kv.mail:
			print('"{:s} ({:s} von {:s})" <{:s}>'.format(kv.name, kv.function, kv.club, kv.mail))
		else:
			print('{:s} does not have E-Mail!'.format(kv.name))
	print('\n')
	print('\n----')
	print('Alle:')
	for kv in wp.getAllMembers():
		if kv.mail:
			print('"{:s} ({:s} von {:s})" <{:s}>'.format(kv.name, kv.function, kv.club, kv.mail))
	print('\n----')

	print('Beiträge:')
	money = 0.00
	for c in wp._clubs:
		print(
			'{club} has {member:d} so needs to pay {pay:.2f} Euro'.format(
				club=c.name, 
				member=c.statistic.getTotalPayingKV(), 
				pay=c.statistic.getTotalPayingKV()
			)
		)
		money += float(c.statistic.getTotalPayingKV())

	print('In total KV gets {:.2f} Euro.'.format(money))
