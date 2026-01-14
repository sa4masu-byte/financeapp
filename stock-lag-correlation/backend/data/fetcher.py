"""
株価データ取得モジュール
- 東証プライム時価総額上位300銘柄の取得
- Stooqを使用した株価データダウンロード
"""
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import requests
from bs4 import BeautifulSoup
import pandas as pd
import pandas_datareader.data as pdr
from tqdm import tqdm
from sqlalchemy.orm import Session
from sqlalchemy import text

import sys
sys.path.append('..')
from config import get_settings, to_stooq_ticker
from models import Ticker, DailyPrice

logger = logging.getLogger(__name__)
settings = get_settings()


class DataFetcher:
    """株価データ取得クラス"""

    def __init__(self, db_session: Session):
        self.session = db_session
        self.retry_delays = settings.stooq_retry_delays
        self.request_delay = settings.stooq_request_delay

    def get_prime_300_tickers(self) -> List[Dict[str, str]]:
        """
        東証プライム時価総額上位300銘柄を取得
        JPXのWebサイトからスクレイピング

        Returns:
            List[Dict]: [{"ticker_code": "7203", "company_name": "トヨタ自動車", "sector": "輸送用機器"}, ...]
        """
        logger.info("東証プライム300銘柄を取得中...")

        # JPX市場構成銘柄一覧ページ（TOPIX Core30, Large70, Mid400など）
        # 注: 実際のJPXサイト構造に合わせて調整が必要
        url = "https://www.jpx.co.jp/markets/indices/topix/tvdivq00000030ne-att/topix_weight_j.csv"

        try:
            # CSVファイルを直接ダウンロード
            df = pd.read_csv(url, encoding='shift_jis')

            # カラム名を正規化
            df.columns = df.columns.str.strip()

            # 時価総額でソートして上位300銘柄を取得
            # 注: 実際のカラム名はJPXのCSV形式に依存
            if '銘柄コード' in df.columns or 'コード' in df.columns:
                code_col = '銘柄コード' if '銘柄コード' in df.columns else 'コード'
                name_col = '銘柄名' if '銘柄名' in df.columns else '会社名'
                sector_col = '業種' if '業種' in df.columns else '33業種区分'

                tickers = []
                for _, row in df.head(300).iterrows():
                    tickers.append({
                        'ticker_code': str(row[code_col]).strip(),
                        'company_name': str(row.get(name_col, '')).strip(),
                        'sector': str(row.get(sector_col, '')).strip()
                    })

                logger.info(f"{len(tickers)}銘柄を取得しました")
                return tickers

        except Exception as e:
            logger.warning(f"JPXからの取得に失敗: {e}")
            logger.info("代替方法でプライム銘柄を取得します...")

        # 代替方法: yfinanceでTOPIX100構成銘柄などから取得
        return self._get_tickers_from_alternative()

    def _get_tickers_from_alternative(self) -> List[Dict[str, str]]:
        """
        代替方法: 主要銘柄リストを取得
        TOPIX Core30, Large70などの構成銘柄から構築
        """
        # 代表的な大型株（手動リスト - 実運用時は定期更新が必要）
        major_tickers = [
            # TOPIX Core30 相当
            ("7203", "トヨタ自動車", "輸送用機器"),
            ("9984", "ソフトバンクグループ", "情報・通信業"),
            ("6758", "ソニーグループ", "電気機器"),
            ("8306", "三菱UFJフィナンシャル・グループ", "銀行業"),
            ("9432", "日本電信電話", "情報・通信業"),
            ("6861", "キーエンス", "電気機器"),
            ("6501", "日立製作所", "電気機器"),
            ("7974", "任天堂", "その他製品"),
            ("8035", "東京エレクトロン", "電気機器"),
            ("9433", "KDDI", "情報・通信業"),
            ("4063", "信越化学工業", "化学"),
            ("6902", "デンソー", "輸送用機器"),
            ("8411", "みずほフィナンシャルグループ", "銀行業"),
            ("8316", "三井住友フィナンシャルグループ", "銀行業"),
            ("6098", "リクルートホールディングス", "サービス業"),
            ("9434", "ソフトバンク", "情報・通信業"),
            ("4519", "中外製薬", "医薬品"),
            ("6367", "ダイキン工業", "機械"),
            ("7267", "本田技研工業", "輸送用機器"),
            ("4568", "第一三共", "医薬品"),
            ("8058", "三菱商事", "卸売業"),
            ("4502", "武田薬品工業", "医薬品"),
            ("6954", "ファナック", "電気機器"),
            ("8766", "東京海上ホールディングス", "保険業"),
            ("9983", "ファーストリテイリング", "小売業"),
            ("3382", "セブン&アイ・ホールディングス", "小売業"),
            ("8031", "三井物産", "卸売業"),
            ("2914", "日本たばこ産業", "食料品"),
            ("6273", "SMC", "機械"),
            ("4503", "アステラス製薬", "医薬品"),
            # Large70 相当（一部）
            ("7751", "キヤノン", "電気機器"),
            ("6594", "日本電産", "電気機器"),
            ("6981", "村田製作所", "電気機器"),
            ("7741", "HOYA", "精密機器"),
            ("4901", "富士フイルムホールディングス", "化学"),
            ("6752", "パナソニック", "電気機器"),
            ("7201", "日産自動車", "輸送用機器"),
            ("8801", "三井不動産", "不動産業"),
            ("8802", "三菱地所", "不動産業"),
            ("9020", "東日本旅客鉄道", "陸運業"),
            ("9022", "東海旅客鉄道", "陸運業"),
            ("5108", "ブリヂストン", "ゴム製品"),
            ("6762", "TDK", "電気機器"),
            ("6503", "三菱電機", "電気機器"),
            ("7733", "オリンパス", "精密機器"),
            ("4661", "オリエンタルランド", "サービス業"),
            ("6326", "クボタ", "機械"),
            ("4523", "エーザイ", "医薬品"),
            ("2802", "味の素", "食料品"),
            ("6701", "NEC", "電気機器"),
            # Mid400 相当（一部）
            ("2801", "キッコーマン", "食料品"),
            ("4452", "花王", "化学"),
            ("6506", "安川電機", "電気機器"),
            ("7269", "スズキ", "輸送用機器"),
            ("8591", "オリックス", "その他金融業"),
            ("6971", "京セラ", "電気機器"),
            ("9613", "NTTデータ", "情報・通信業"),
            ("4543", "テルモ", "精密機器"),
            ("7270", "SUBARU", "輸送用機器"),
            ("6857", "アドバンテスト", "電気機器"),
            ("6146", "ディスコ", "機械"),
            ("6920", "レーザーテック", "電気機器"),
            ("7832", "バンダイナムコホールディングス", "その他製品"),
            ("4385", "メルカリ", "情報・通信業"),
            ("6479", "ミネベアミツミ", "電気機器"),
            ("3659", "ネクソン", "情報・通信業"),
            ("6988", "日東電工", "化学"),
            ("7011", "三菱重工業", "機械"),
            ("5713", "住友金属鉱山", "非鉄金属"),
            ("4704", "トレンドマイクロ", "情報・通信業"),
            # 追加銘柄
            ("8267", "イオン", "小売業"),
            ("2502", "アサヒグループホールディングス", "食料品"),
            ("2503", "キリンホールディングス", "食料品"),
            ("4507", "塩野義製薬", "医薬品"),
            ("6753", "シャープ", "電気機器"),
            ("7182", "ゆうちょ銀行", "銀行業"),
            ("8725", "MS&ADインシュアランスグループ", "保険業"),
            ("8750", "第一生命ホールディングス", "保険業"),
            ("9021", "西日本旅客鉄道", "陸運業"),
            ("9101", "日本郵船", "海運業"),
            ("5401", "日本製鉄", "鉄鋼"),
            ("5802", "住友電気工業", "非鉄金属"),
            ("6702", "富士通", "電気機器"),
            ("9735", "セコム", "サービス業"),
            ("4528", "小野薬品工業", "医薬品"),
            ("6301", "小松製作所", "機械"),
            ("4911", "資生堂", "化学"),
            ("9766", "コナミグループ", "情報・通信業"),
            ("3861", "王子ホールディングス", "パルプ・紙"),
            ("5201", "AGC", "ガラス・土石製品"),
        ]

        tickers = [
            {"ticker_code": code, "company_name": name, "sector": sector}
            for code, name, sector in major_tickers
        ]

        logger.info(f"代替リストから{len(tickers)}銘柄を取得しました")
        return tickers

    def download_ticker_data(
        self,
        ticker: str,
        years: int = 10
    ) -> Optional[pd.DataFrame]:
        """
        単一銘柄のデータ取得（リトライ機能付き）
        Stooqを使用

        Args:
            ticker: 銘柄コード（例: "7203"）
            years: 取得年数（デフォルト: 10年）

        Returns:
            DataFrame with columns: [adj_close, volume] or None
        """
        stooq_ticker = to_stooq_ticker(ticker)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years * 365)

        for attempt, delay in enumerate(self.retry_delays):
            try:
                df = pdr.DataReader(stooq_ticker, 'stooq', start=start_date, end=end_date)

                if df.empty:
                    logger.warning(f"{ticker}: データが空です")
                    return None

                # Stooqは降順なので昇順に並び替え
                df = df.sort_index()

                # 必要なカラムのみ抽出
                result = pd.DataFrame({
                    'adj_close': df['Close'],
                    'volume': df['Volume'].astype(int) if 'Volume' in df.columns else 0
                })
                result.index = pd.to_datetime(result.index).date

                time.sleep(self.request_delay)
                return result

            except Exception as e:
                logger.warning(f"{ticker}: 取得失敗 (試行{attempt + 1}): {e}")
                if attempt < len(self.retry_delays) - 1:
                    time.sleep(delay)

        logger.error(f"{ticker}: 全リトライ失敗")
        return None

    def download_all_tickers(
        self,
        tickers: List[str],
        years: int = 10
    ) -> Dict[str, pd.DataFrame]:
        """
        全銘柄一括ダウンロード

        Args:
            tickers: 銘柄コードリスト
            years: 取得年数

        Returns:
            Dict[ticker_code, DataFrame]
        """
        results = {}
        failed = []

        batch_size = settings.stooq_batch_size

        for i in tqdm(range(0, len(tickers), batch_size), desc="バッチ処理"):
            batch = tickers[i:i + batch_size]

            for ticker in tqdm(batch, desc=f"バッチ {i // batch_size + 1}", leave=False):
                df = self.download_ticker_data(ticker, years)
                if df is not None:
                    results[ticker] = df
                else:
                    failed.append(ticker)

            # バッチ間に追加の休憩
            if i + batch_size < len(tickers):
                time.sleep(2)

        # サマリー表示
        logger.info(f"=== ダウンロード完了 ===")
        logger.info(f"成功: {len(results)}銘柄")
        logger.info(f"失敗: {len(failed)}銘柄")
        if failed:
            logger.info(f"失敗銘柄: {failed[:10]}..." if len(failed) > 10 else f"失敗銘柄: {failed}")

        return results

    def download_topix(self, years: int = 10) -> Optional[pd.Series]:
        """
        TOPIXデータ取得（Stooq使用）

        Returns:
            Series of TOPIX adjusted close prices
        """
        # StooqでのTOPIXティッカー
        topix_ticker = "^TPX"
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years * 365)

        for attempt, delay in enumerate(self.retry_delays):
            try:
                df = pdr.DataReader(topix_ticker, 'stooq', start=start_date, end=end_date)

                if df.empty:
                    logger.warning("TOPIX: データが空です")
                    # 代替: 1306（TOPIX連動ETF）を試行
                    return self._download_topix_etf(years)

                # Stooqは降順なので昇順に並び替え
                df = df.sort_index()
                result = df['Close']
                result.index = pd.to_datetime(result.index).date
                return result

            except Exception as e:
                logger.warning(f"TOPIX取得失敗 (試行{attempt + 1}): {e}")
                if attempt < len(self.retry_delays) - 1:
                    time.sleep(delay)

        # 代替手段
        return self._download_topix_etf(years)

    def _download_topix_etf(self, years: int = 10) -> Optional[pd.Series]:
        """
        TOPIX連動ETF（1306）からTOPIX代替データを取得（Stooq使用）
        """
        logger.info("TOPIX連動ETF(1306)を代替として使用")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years * 365)

        try:
            df = pdr.DataReader("1306.JP", 'stooq', start=start_date, end=end_date)
            if not df.empty:
                df = df.sort_index()
                result = df['Close']
                result.index = pd.to_datetime(result.index).date
                return result
        except Exception as e:
            logger.error(f"TOPIX ETF取得も失敗: {e}")

        return None

    def save_tickers_to_db(self, tickers: List[Dict[str, str]]):
        """
        Save ticker master data to DB (upsert)
        """
        for ticker_info in tickers:
            existing = self.session.query(Ticker).filter(
                Ticker.ticker_code == ticker_info['ticker_code']
            ).first()

            if existing:
                existing.company_name = ticker_info['company_name']
                existing.sector = ticker_info.get('sector', '')
                existing.market_cap = ticker_info.get('market_cap')
            else:
                self.session.add(Ticker(
                    ticker_code=ticker_info['ticker_code'],
                    company_name=ticker_info['company_name'],
                    sector=ticker_info.get('sector', ''),
                    market_cap=ticker_info.get('market_cap')
                ))

        self.session.commit()
        logger.info(f"{len(tickers)} tickers saved to DB")

    def save_prices_to_db(self, ticker: str, df: pd.DataFrame):
        """
        Save daily price data to DB (upsert)
        """
        if df is None or df.empty:
            return

        for date_val, row in df.iterrows():
            existing = self.session.query(DailyPrice).filter(
                DailyPrice.ticker_code == ticker,
                DailyPrice.date == date_val
            ).first()

            adj_close = float(row['adj_close'])
            volume = int(row['volume']) if pd.notna(row['volume']) else None

            if existing:
                existing.adj_close = adj_close
                existing.volume = volume
            else:
                self.session.add(DailyPrice(
                    ticker_code=ticker,
                    date=date_val,
                    adj_close=adj_close,
                    volume=volume
                ))

        self.session.commit()

    def get_tickers_from_db(self) -> List[str]:
        """
        DBから銘柄コードリストを取得
        """
        tickers = self.session.query(Ticker.ticker_code).all()
        return [t[0] for t in tickers]

    def get_ticker_info(self, ticker_code: str) -> Optional[Tuple[str, str]]:
        """
        銘柄情報を取得

        Returns:
            (company_name, sector) or None
        """
        ticker = self.session.query(Ticker).filter(
            Ticker.ticker_code == ticker_code
        ).first()

        if ticker:
            return (ticker.company_name, ticker.sector)
        return None
