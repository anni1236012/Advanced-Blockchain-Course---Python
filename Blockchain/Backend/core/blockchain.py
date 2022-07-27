""" 
Copyright (c) 2021 Codiesalert.com
These scripts should be used for commercial purpose without Codies Alert Permission
Any violations may lead to legal action
"""
import sys

sys.path.append("/Users/Vmaha/Desktop/Bitcoin")

import copy
import configparser
from Blockchain.Backend.core.block import Block
from Blockchain.Backend.core.blockheader import BlockHeader
from Blockchain.Backend.util.util import hash256, merkle_root, target_to_bits, bits_to_target
from Blockchain.Backend.core.database.database import BlockchainDB, NodeDB
from Blockchain.Backend.core.Tx import CoinbaseTx, Tx
from multiprocessing import Process, Manager
from Blockchain.Frontend.run import main
from Blockchain.Backend.core.network.syncManager import syncManager
from Blockchain.client.autoBroadcastTX import autoBroadcast
import time

ZERO_HASH = "0" * 64
VERSION = 1
INITIAL_TARGET = 0x0000FFFF00000000000000000000000000000000000000000000000000000000
MAX_TARGET     = 0x0000ffff00000000000000000000000000000000000000000000000000000000

"""
# Calculate new Target to keep our Block mine time under 20 seconds
# Reset Block Difficulty after every 10 Blocks
"""
AVERAGE_BLOCK_MINE_TIME = 20
RESET_DIFFICULTY_AFTER_BLOCKS = 10
AVERAGE_MINE_TIME = AVERAGE_BLOCK_MINE_TIME * RESET_DIFFICULTY_AFTER_BLOCKS

class Blockchain:
    def __init__(self, utxos, MemPool, newBlockAvailable, secondryChain):
        self.utxos = utxos
        self.MemPool = MemPool
        self.newBlockAvailable = newBlockAvailable
        self.secondryChain = secondryChain
        self.current_target = INITIAL_TARGET
        self.bits = target_to_bits(INITIAL_TARGET)

    def write_on_disk(self, block):
        blockchainDB = BlockchainDB()
        blockchainDB.write(block)

    def fetch_last_block(self):
        blockchainDB = BlockchainDB()
        return blockchainDB.lastBlock()

    def GenesisBlock(self):
        BlockHeight = 0
        prevBlockHash = ZERO_HASH
        self.addBlock(BlockHeight, prevBlockHash)

    """ Start the Sync Node """
    def startSync(self, block = None):
        try:
            node = NodeDB()
            portList = node.read()

            for port in portList:
                if localHostPort != port:
                    sync = syncManager(localHost, port, secondryChain = self.secondryChain)
                    try:
                        if block:
                            sync.publishBlock(localHostPort - 1, port, block) 
                        else:                    
                            sync.startDownload(localHostPort - 1, port, True)
                  
                    except Exception as err:
                        pass
                    
        except Exception as err:
            pass
       
    """ Keep Track of all the unspent Transaction in cache memory for fast retrival"""
    def store_uxtos_in_cache(self):
        for tx in self.addTransactionsInBlock:
            print(f"Transaction added {tx.TxId} ")
            self.utxos[tx.TxId] = tx

    def remove_spent_Transactions(self):
        for txId_index in self.remove_spent_transactions:
            if txId_index[0].hex() in self.utxos:

                if len(self.utxos[txId_index[0].hex()].tx_outs) < 2:
                    print(f" Spent Transaction removed {txId_index[0].hex()} ")
                    del self.utxos[txId_index[0].hex()]
                else:
                    prev_trans = self.utxos[txId_index[0].hex()]
                    self.utxos[txId_index[0].hex()] = prev_trans.tx_outs.pop(
                        txId_index[1]
                    )
                    
    """ Check if it is a double spending Attempt """
    def doubleSpendingAttempt(self, tx):
        for txin in tx.tx_ins:
            if txin.prev_tx not in self.prevTxs and txin.prev_tx.hex() in self.utxos:
                self.prevTxs.append(txin.prev_tx)
            else:
                return True

    """ Read Transactions from Memory Pool"""
    def read_transaction_from_memorypool(self):
        self.Blocksize = 80
        self.TxIds = []
        self.addTransactionsInBlock = []
        self.remove_spent_transactions = []
        self.prevTxs = []
        deleteTxs = []

        tempMemPool = dict(self.MemPool)
        
        if self.Blocksize < 1000000:
            for tx in tempMemPool:
                if not self.doubleSpendingAttempt(tempMemPool[tx]):
                    tempMemPool[tx].TxId = tx
                    self.TxIds.append(bytes.fromhex(tx))
                    self.addTransactionsInBlock.append(tempMemPool[tx])
                    self.Blocksize += len(tempMemPool[tx].serialize())

                    for spent in tempMemPool[tx].tx_ins:
                        self.remove_spent_transactions.append([spent.prev_tx, spent.prev_index])
                else:
                    deleteTxs.append(tx)
        
        for txId in deleteTxs:
            del self.MemPool[txId]

           
    """ Remove Transactions from Memory pool """
    def remove_transactions_from_memorypool(self):
        for tx in self.TxIds:
            if tx.hex() in self.MemPool:
                del self.MemPool[tx.hex()]

    def convert_to_json(self):
        self.TxJson = []
        for tx in self.addTransactionsInBlock:
            self.TxJson.append(tx.to_dict())

    def calculate_fee(self):
        self.input_amount = 0
        self.output_amount = 0
        """ Calculate Input Amount """
        for TxId_index in self.remove_spent_transactions:
            if TxId_index[0].hex() in self.utxos:
                self.input_amount += (
                    self.utxos[TxId_index[0].hex()].tx_outs[TxId_index[1]].amount
                )

        """ Calculate Output Amount """
        for tx in self.addTransactionsInBlock:
            for tx_out in tx.tx_outs:
                self.output_amount += tx_out.amount

        self.fee = self.input_amount - self.output_amount

    def buildUTXOS(self):
        allTxs = {}
        blocks = BlockchainDB().read()

        for block in blocks:
            for tx in block['Txs']:
                allTxs[tx['TxId']] = tx
            
        for block in blocks:
            for tx in block['Txs']:
                for txin in tx['tx_ins']:
                    if txin['prev_tx'] != "0000000000000000000000000000000000000000000000000000000000000000":
                        if len(allTxs[txin['prev_tx']]['tx_outs']) < 2:
                            del allTxs[txin['prev_tx']]
                        else:
                            txOut = allTxs[txin['prev_tx']]['tx_outs']
                            txOut.pop(txin['prev_index'])
        
        for tx in allTxs:
            self.utxos[tx] = Tx.to_obj(allTxs[tx])


    def settargetWhileBooting(self):
        bits, timestamp = self.getTargetDifficultyAndTimestamp()
        self.bits = bytes.fromhex(bits)
        self.current_target = bits_to_target(self.bits)

    def getTargetDifficultyAndTimestamp(self, BlockHeight = None):
        if BlockHeight:
            blocks = BlockchainDB().read()
            bits = blocks[BlockHeight]['BlockHeader']['bits']
            timestamp = blocks[BlockHeight]['BlockHeader']['timestamp']
        else:
            block = BlockchainDB().lastBlock()
            bits = block['BlockHeader']['bits']
            timestamp = block['BlockHeader']['timestamp']
        return bits, timestamp


    def adjustTargetDifficulty(self, BlockHeight):
        if BlockHeight % 10 == 0:
            bits, timestamp = self.getTargetDifficultyAndTimestamp(BlockHeight - 10)
            Lastbits, lastTimestamp = self.getTargetDifficultyAndTimestamp()

            lastTarget = bits_to_target(bytes.fromhex(bits))
            AverageBlockMineTime = lastTimestamp - timestamp
            timeRatio = AverageBlockMineTime / AVERAGE_MINE_TIME

            NEW_TARGET = int(format(int(lastTarget * timeRatio)))

            if NEW_TARGET > MAX_TARGET:
                NEW_TARGET = MAX_TARGET
            
            self.bits = target_to_bits(NEW_TARGET)
            self.current_target = NEW_TARGET

    def BroadcastBlock(self, block):
        self.startSync(block)

    def LostCompetition(self):
        deleteBlock = []
        tempBlocks = dict(self.newBlockAvailable)

        for newblock in tempBlocks:
            block = tempBlocks[newblock]
            deleteBlock.append(newblock)
        
            BlockHeaderObj = BlockHeader(block.BlockHeader.version,
                                block.BlockHeader.prevBlockHash, 
                                block.BlockHeader.merkleRoot, 
                                block.BlockHeader.timestamp,
                                block.BlockHeader.bits,
                                block.BlockHeader.nonce)

            if BlockHeaderObj.validateBlock():
                for idx, tx in enumerate(block.Txs):
                    self.utxos[tx.id()] = tx.serialize()
                    block.Txs[idx].TxId = tx.id()

                    """ Remove Spent Transactions """
                    for txin in tx.tx_ins:
                        if txin.prev_tx.hex() in self.utxos:
                            del self.utxos[txin.prev_tx.hex()]

                    if tx.id() in self.MemPool:
                        del self.MemPool[tx.id()]

                    block.Txs[idx] = tx.to_dict()
                    
                block.BlockHeader.to_hex()
                BlockchainDB().write([block.to_dict()])
            else:
                """ Resolve the Conflict b/w ther Miners """
                orphanTxs = {}
                validTxs = {}
                if self.secondryChain:
                    addBlocks = []
                    addBlocks.append(block)
                    prevBlockhash = block.BlockHeader.prevBlockHash.hex()
                    count = 0

                    while count != len(self.secondryChain):
                        if prevBlockhash in self.secondryChain:
                            addBlocks.append(self.secondryChain[prevBlockhash])
                            prevBlockhash = self.secondryChain[prevBlockhash].BlockHeader.prevBlockHash.hex()
                        count += 1
                    
                    blockchain = BlockchainDB().read()
                    lastValidBlock = blockchain[-len(addBlocks)]

                    if lastValidBlock['BlockHeader']['blockHash'] == prevBlockhash:
                        for i in range(len(addBlocks) - 1):
                            orphanBlock = blockchain.pop()

                            for tx in orphanBlock['Txs']:
                                if tx['TxId'] in self.utxos:
                                    del self.utxos[tx['TxId']]

                                    """ Don't Include COINBASE TX because it didn't come from MEMPOOL"""
                                    if tx['tx_ins'][0]['prev_tx'] != "0000000000000000000000000000000000000000000000000000000000000000":
                                        orphanTxs[tx['TxId']] = tx

                        BlockchainDB().update(blockchain)
                        
                        for Bobj in addBlocks[::-1]:
                            validBlock = copy.deepcopy(Bobj)
                            validBlock.BlockHeader.to_hex()

                            for index, tx in enumerate(validBlock.Txs):
                                validBlock.Txs[index].TxId = tx.id()
                                self.utxos[tx.id()] = tx

                                """ Remove Spent Transactions """
                                for txin in tx.tx_ins:
                                    if txin.prev_tx.hex() in self.utxos:
                                        del self.utxos[txin.prev_tx.hex()]
                                
                                if tx.tx_ins[0].prev_tx.hex() != "0000000000000000000000000000000000000000000000000000000000000000":
                                    validTxs[validBlock.Txs[index].TxId] = tx

                                validBlock.Txs[index] = tx.to_dict()
                            
                            BlockchainDB().write([validBlock.to_dict()])
                        
                        """ Add Transactoins Back to MemPool """
                        for TxId in orphanTxs:
                            if TxId not in validTxs:
                                self.MemPool[TxId] = Tx.to_obj(orphanTxs[TxId])

                self.secondryChain[newblock] = block

        
        for blockHash in deleteBlock:
            del self.newBlockAvailable[blockHash]

    def addBlock(self, BlockHeight, prevBlockHash):
        self.read_transaction_from_memorypool()
        self.calculate_fee()
        timestamp = int(time.time())
        coinbaseInstance = CoinbaseTx(BlockHeight)
        coinbaseTx = coinbaseInstance.CoinbaseTransaction()
        self.Blocksize += len(coinbaseTx.serialize())

        coinbaseTx.tx_outs[0].amount = coinbaseTx.tx_outs[0].amount + self.fee

        self.TxIds.insert(0, bytes.fromhex(coinbaseTx.id()))
        self.addTransactionsInBlock.insert(0, coinbaseTx)

        merkleRoot = merkle_root(self.TxIds)[::-1].hex()
        self.adjustTargetDifficulty(BlockHeight)
        blockheader = BlockHeader(
            VERSION, prevBlockHash, merkleRoot, timestamp, self.bits, nonce = 0
        )
        competitionOver = blockheader.mine(self.current_target, self.newBlockAvailable)

        if competitionOver:
            self.LostCompetition()
        else:
            newBlock = Block(BlockHeight, self.Blocksize, blockheader, len(self.addTransactionsInBlock),
                            self.addTransactionsInBlock)
            blockheader.to_bytes()
            block = copy.deepcopy(newBlock)
            broadcastNewBlock = Process(target = self.BroadcastBlock, args = (block, ))
            broadcastNewBlock.start()
            blockheader.to_hex()
            self.remove_spent_Transactions()
            self.remove_transactions_from_memorypool()
            self.store_uxtos_in_cache()
            self.convert_to_json()

            print(
                f"Block {BlockHeight} mined successfully with Nonce value of {blockheader.nonce}"
            )
            self.write_on_disk(
                [
                    Block(
                        BlockHeight, self.Blocksize, blockheader.__dict__, len(self.TxJson), self.TxJson
                    ).__dict__
                ]
            )

    def main(self):
        lastBlock = self.fetch_last_block()
        if lastBlock is None:
            self.GenesisBlock()

        while True:
            lastBlock = self.fetch_last_block()
            BlockHeight = lastBlock["Height"] + 1
            print(f"Current Block Height is is {BlockHeight}")
            prevBlockHash = lastBlock["BlockHeader"]["blockHash"]
            self.addBlock(BlockHeight, prevBlockHash)
            
if __name__ == "__main__":
    
    """ read configuration file """
    config = configparser.ConfigParser()
    config.read('config.ini')
    localHost = config['DEFAULT']['host']
    localHostPort = int(config['MINER']['port'])
    simulateBTC = bool(config['MINER']['simulateBTC'])
    webport = int(config['Webhost']['port'])

    with Manager() as manager:
        utxos = manager.dict()
        MemPool = manager.dict()
        newBlockAvailable = manager.dict()
        secondryChain = manager.dict()
        
        webapp = Process(target=main, args=(utxos, MemPool, webport, localHostPort))
        webapp.start()
        
        """ Start Server and Listen for miner requests """
        sync = syncManager(localHost, localHostPort, newBlockAvailable, secondryChain, MemPool)
        startServer = Process(target = sync.spinUpTheServer)
        startServer.start()

        blockchain = Blockchain(utxos, MemPool, newBlockAvailable, secondryChain)
        blockchain.startSync()
        blockchain.buildUTXOS()

        if simulateBTC:
            autoBroadcastTxs = Process(target = autoBroadcast)
            autoBroadcastTxs.start()

        blockchain.settargetWhileBooting()
        blockchain.main()
