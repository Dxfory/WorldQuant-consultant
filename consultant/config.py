"""
Zach
Zheng Xing
"""
import os
import sys

if getattr(sys, 'frozen', False):
    ROOT_PATH = sys._MEIPASS
else:
    ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
RECORDS_PATH = os.path.join(ROOT_PATH, 'records')

REGION_LIST = ['USA', 'GLB', 'EUR', 'ASI', 'CHN']
DELAY_LIST = [1, 0]
INSTRUMENT_TYPE_LIST = ['EQUITY', 'CRYPTO']
DATASET_CATEGORY_LIST = ['pv', 'fundamental', 'analyst', 'socialmedia', 'news', 'option', 'model', 'shortinterest', 'institutions', 'other', 'sentiment', 'insiders', 'earnings', 'macro', 'imbalance', 'risk']
UNIVERSE_DICT = {
    "instrumentType": {
        "EQUITY": {
            "region": {
                "USA": [
                    "TOP3000", "TOP1000", "TOP500", "TOP200", "ILLIQUID_MINVOL1M", "TOPSP500",
                ],
                "GLB": [
                    "TOP3000", "MINVOL1M",
                ],
                "EUR": [
                    "TOP2500", "TOP1200", "TOP800", "TOP400", "ILLIQUID_MINVOL1M",
                ],
                "ASI": [
                    "MINVOL1M", "ILLIQUID_MINVOL1M",
                ],
                "CHN": [
                    "TOP2000U",
                ],
                "KOR": [
                    "TOP600",
                ],
                "TWN": [
                    "TOP500", "TOP100",
                ],
                "HKG": [
                    "TOP800", "TOP500",
                ],
                "JPN": [
                    "TOP1600", "TOP1200",
                ],
                "AMR": [
                    "TOP600",
                ]
            }
        },
        "CRYPTO": {
            "region": {
                "GLB": [
                    "TOP50", "TOP20", "TOP10", "TOP5",
                ]
            }
        }
    }
}
UNIVERSE_UNIQUE = ['TOP2000U', 'TOP1200', 'TOP800', 'ILLIQUID_MINVOL1M', 'TOP100', 'TOP500', 'TOP1600', 'TOP600',
                   'TOPSP500', 'TOP1000', 'TOP3000', 'TOP200', 'MINVOL1M', 'TOP400']

os.makedirs(RECORDS_PATH, exist_ok=True)

