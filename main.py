import csv
import requests
import time
import logging
import os
import json
from requests.auth import HTTPBasicAuth
from datetime import datetime

def load_config():
    try:
        with open('config.json', 'r') as file:
            config = json.load(file)
        logging.info("成功載入配置文件")
        return config
    except FileNotFoundError:
        raise FileNotFoundError("找不到 config.json 文件")
    except json.JSONDecodeError:
        raise ValueError("config.json 格式錯誤，請檢查 JSON 格式")
    except Exception as e:
        raise Exception(f"載入配置文件時發生錯誤: {str(e)}")

def setup_logging():
    """設置日誌記錄"""
    # 創建logs目錄（如果不存在）
    log_dir = "adata_fs_automation_logs"
    os.makedirs(log_dir, exist_ok=True)

    # 設置日誌文件名（包含時間戳）adata_fs_automation_logs/ticket_update_20240101_143045.log
    log_filename = os.path.join(
        log_dir,
        f'ticket_update_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    )

    # 設置日誌格式，之後的 logging 調用都會使用這個配置
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        #Handler 決定日誌訊息要輸出到哪裡
        handlers=[ 
            # 文件處理器，將日誌寫入到文件中
            logging.FileHandler(log_filename, encoding='utf-8'),
            # 控制台處理器，將日誌輸出到控制台（終端）用於即時查看日誌
            logging.StreamHandler()
        ]
    )

    logging.info(f"日誌文件位置: {os.path.abspath(log_filename)}")
    return log_filename

class TicketUpdater:
    def __init__(self, username, password, base_url):
        self.auth = HTTPBasicAuth(username, password)
        self.base_url = base_url
        self.session = requests.Session()
        self.session.auth = self.auth
        self.success_count = 0
        self.failure_count = 0
        self.error_tickets = []  # 記錄失敗的ticket ID

    def update_ticket(self, ticket_id):
        check_url = f"{self.base_url}/{ticket_id}"
        
        try:
            check_response = self.session.get(check_url)
            check_response.raise_for_status()
            ticket_data = check_response.json()
        
            # 取得send_to_dxdb_statuscode欄位
            status_code = ticket_data.get('ticket', {}).get('custom_fields', {}).get('send_to_dxdb_statuscode')
            
            # 如果狀態碼是 200，則跳過此 ticket。當執行到 return True 時，函數立即結束。
            if status_code == 200:
                logging.info(f"Ticket {ticket_id} 的 send_to_dxdb_statuscode 已是 200，跳過更新")
                return True 
            else:
                #更新單個ticket的函數
                url = f"{self.base_url}/{ticket_id}/?bypass_mandatory=true"
                payload = {
                    "custom_fields": {
                        "trigger_mc_workflow_to_update_dxdb_via_api": True
                    }
                }

                response = self.session.put(url, json=payload)
                response.raise_for_status() #檢查 HTTP 響應的狀態碼
                self.success_count += 1
                logging.info(f"成功更新 Ticket {ticket_id}")
                return True
        except requests.exceptions.RequestException as e: # 捕獲所有可能的請求異常
            self.failure_count += 1
            self.error_tickets.append(ticket_id)  # 記錄失敗的ticket ID
            logging.error(f"更新 Ticket {ticket_id} 時發生錯誤: {str(e)}")
            return False

    def process_csv(self, csv_file_path, delay=5):
        """處理CSV文件中的所有tickets"""
        try:
            ticket_ids = []
            with open(csv_file_path, 'r') as file:
                csv_reader = csv.reader(file) #返回一個迭代器物件。每次迭代返回一個列表,代表 CSV 文件中的一行
                # 跳過標題行
                next(csv_reader)
                # 讀取所有ticket IDs（只讀第一列）
                for row in csv_reader:
                    if row and row[0].strip():  # 確保行不為空且第一個欄位有值
                        ticket_ids.append(row[0].strip())

            if not ticket_ids: #如果 ticket_ids 是空列表
                logging.error("CSV文件中沒有找到有效的Ticket IDs")
                return

            total_tickets = len(ticket_ids)
            logging.info(f"開始處理，總計 {total_tickets} 個 tickets")
            logging.info(f"第一個Ticket ID: {ticket_ids[0]}")
            logging.info(f"最後一個Ticket ID: {ticket_ids[-1]}")

            for index, ticket_id in enumerate(ticket_ids, 1):
                logging.info(f"處理進度: {index}/{total_tickets} ({(index/total_tickets)*100:.2f}%)")
                self.update_ticket(ticket_id)
                
                if index < total_tickets:  # 不在最後一個請求後等待
                    time.sleep(delay)

            # 處理完成後，記錄失敗的cases
            if self.error_tickets:
                error_log = os.path.join('logs', 'error_tickets.txt')
                with open(error_log, 'w') as f:
                    f.write('\n'.join(self.error_tickets))
                logging.info(f"失敗的Ticket ID已記錄到: {error_log}")

            logging.info(f"處理完成！成功: {self.success_count}, 失敗: {self.failure_count}")

        except FileNotFoundError:
            logging.error(f"找不到CSV文件: {csv_file_path}")
        except Exception as e:
            logging.error(f"處理CSV時發生錯誤: {str(e)}")

def main():
    try:
        # 取得配置值
        config = load_config()
        credentials = config.get('credentials', {})
        api = config.get('api', {})
        csv = config.get('csv', {})   
    
        # 設置日誌
        log_file = setup_logging()
        logging.info(f"開始執行程式")
        
        updater = TicketUpdater(
            username=credentials['username'],
            password=credentials['password'],
            base_url=api['base_url']
        )
        updater.process_csv(csv_file_path=csv['file_path'])
        
        logging.info(f"程式執行完成，日誌文件位置: {log_file}")
    except Exception as e:
        logging.error(f"程式執行時發生未預期的錯誤: {str(e)}")

if __name__ == "__main__":
    main()