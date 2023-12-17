""" 
Copyright (c) 2021 Codiesalert.com
These scripts should be used for commercial purpose without Codies Alert Permission
Any violations may lead to legal action
"""
from flask import Flask, render_template, request, redirect, url_for
from Blockchain.client.sendBTC import SendBTC
from Blockchain.Backend.core.Tx import Tx
from Blockchain.Backend.core.database.database import BlockchainDB, NodeDB
from Blockchain.Backend.util.util import encode_base58, decode_base58
from Blockchain.Backend.core.network.syncManager import syncManager
from hashlib import sha256
from multiprocessing import Process
from flask_qrcode import QRcode

app = Flask(__name__)
qrcode = QRcode(app)
main_prefix = b'\x00'
global memoryPool
memoryPool ={}

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/transactions/<txid>')
@app.route('/transactions')
def transactions(txid = None):
    if txid:
        return redirect(url_for('txDetail', txid = txid))
    else:
        ErrorFlag = True
        while ErrorFlag:
            try:
                allTxs = dict(UTXOS)
                ErrorFlag = False
                return render_template("transactions.html",allTransactions = allTxs,refreshtime = 10)
            except:
                ErrorFlag = True
                return render_template('transactions.html', allTransactions={}, refreshtime = 10)

@app.route('/tx/<txid>')
def txDetail(txid):
    blocks = readDatabase()
    for block in blocks:
        for Tx in block['Txs']:
            if Tx['TxId'] == txid:
                return render_template('txDetail.html', Tx=Tx, block = block , encode_base58 = encode_base58,
                bytes = bytes, sha256 = sha256, main_prefix = main_prefix)
    return "<h1> No Results Found </h1>"

@app.route('/mempool')
def mempool():
    try:
        blocks = readDatabase()
        ErrorFlag = True
        while ErrorFlag:
            try: 
                mempooltxs = dict(MEMPOOL)
                ErrorFlag = False
            except:
                ErrorFlag = True

        """" If TxId is not in the Origional list then remove it from the mempool """
        for txid in memoryPool:
            if txid not in mempooltxs:
                del memoryPool[txid]

        """Add the new Tx to the mempool if it is not already there"""
        for Txid in mempooltxs:
            amount = 0
            TxObj = mempooltxs[Txid]      
            matchFound = False

            """ Total Amount """
            for txin in TxObj.tx_ins:
                for block in blocks:
                    for Tx in block['Txs']:
                        if Tx['TxId'] == txin.prev_tx.hex():
                            amount  += Tx['tx_outs'][txin.prev_index]['amount']
                            matchFound = True
                            break
                    if matchFound:
                        matchFound = False
                        break
            memoryPool[TxObj.TxId] = [TxObj.to_dict(), amount/100000000, txin.prev_index]
        return render_template('mempool.html', Txs = memoryPool,refreshtime = 2)

    except Exception as e:
        return render_template('mempool.html', Txs = memoryPool,refreshtime = 2)

@app.route('/memTx/<txid>')
def memTxDetails(txid):
    if txid in memoryPool:
        Tx = memoryPool.get(txid)[0]
        return render_template('txDetail.html', Tx = Tx, refreshtime = 2,
        encode_base58 = encode_base58, bytes = bytes, sha256 = sha256, main_prefix = main_prefix,
        Unconfirmed = True)
    else:
        return redirect(url_for('transactions', txid = txid))
        
@app.route('/search')
def search():
    identifier = request.args.get('search')
    if len(identifier) == 64:
        if identifier[:4] == "0000":
            return redirect(url_for('showBlock', blockHeader = identifier))
        else:
            return redirect(url_for('txDetail', txid = identifier))
    else:
        return redirect(url_for('address', publicAddress = identifier))

""" Read data from the Blockchain """
def readDatabase():
    ErrorFlag = True
    while ErrorFlag:
        try:
            blockchain = BlockchainDB()
            blocks = blockchain.read()
            ErrorFlag = False
        except:
            ErrorFlag = True
            print("Error reading database")
    return blocks

@app.route('/block')
def block():
    header = request.args.get('blockHeader')
    if request.args.get('blockHeader'):
        return redirect(url_for('showBlock', blockHeader=request.args.get('blockHeader')) )
    else:
        blocks = readDatabase()
        return render_template('block.html', blocks=blocks, refreshtime = 10)

@app.route('/block/<blockHeader>')
def showBlock(blockHeader):
    blocks = readDatabase()
    for block in blocks:
        if block['BlockHeader']['blockHash'] == blockHeader:
            return render_template('blockDetails.html', block = block, main_prefix = main_prefix, 
            encode_base58 = encode_base58, bytes = bytes, sha256 = sha256)
    
    return "<h1> Invalid Identifier </h1>"

@app.route('/address/<publicAddress>')
def address(publicAddress):
    if len(publicAddress) < 35 and publicAddress[:1] == "1":
        h160 = decode_base58(publicAddress)

        ErrorFlag = True
        while ErrorFlag:
            try:
                AllUtxos = dict(UTXOS)
                ErrorFlag = False
            except Exception as e:
                ErrorFlag = True
        
        amount = 0
        AccountUtxos = []

        for TxId in AllUtxos:
           for tx_out in AllUtxos[TxId].tx_outs:
            if tx_out.script_pubkey.cmds[2] == h160:
                amount += tx_out.amount
                AccountUtxos.append(AllUtxos[TxId])
        
        return render_template('address.html', Txs = AccountUtxos, amount = amount,
        encode_base58 = encode_base58, bytes = bytes, sha256 = sha256, main_prefix = main_prefix, 
        publicAddress = publicAddress, qrcode = qrcode)
    else:
        return "<h1> Invalid Identifier </h1>"


@app.route("/wallet", methods=["GET", "POST"])
def wallet():
    message = ""
    if request.method == "POST":
        FromAddress = request.form.get("fromAddress")
        ToAddress = request.form.get("toAddress")
        Amount = request.form.get("Amount", type=int)
        sendCoin = SendBTC(FromAddress, ToAddress, Amount, UTXOS)
        TxObj = sendCoin.prepareTransaction()

        scriptPubKey = sendCoin.scriptPubKey(FromAddress)
        verified = True

        if not TxObj:
            message = "Invalid Transaction"

        if isinstance(TxObj, Tx):
            for index, tx in enumerate(TxObj.tx_ins):
                if not TxObj.verify_input(index, scriptPubKey):
                    verified = False

            if verified:
                MEMPOOL[TxObj.TxId] = TxObj
                relayTxs = Process(target = broadcastTx, args = (TxObj, localHostPort)) 
                relayTxs.start()
                message = "Transaction added in memory Pool"

    return render_template("wallet.html", message=message)

def broadcastTx(TxObj, localHostPort = None):
    try:
        node = NodeDB()
        portList = node.read()

        for port in portList:
            if localHostPort != port:
                sync = syncManager('127.0.0.1', port)
                try:
                    sync.connectToHost(localHostPort - 1, port)
                    sync.publishTx(TxObj)
                
                except Exception as err:
                    pass
                
    except Exception as err:
        pass

def main(utxos, MemPool, port, localPort):
    global UTXOS
    global MEMPOOL
    global localHostPort 
    UTXOS = utxos
    MEMPOOL = MemPool
    localHostPort = localPort
    app.run(port = port)
