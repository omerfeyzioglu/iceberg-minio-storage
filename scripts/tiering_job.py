#!/usr/bin/env python3
"""
🔄 Manuel MinIO Tiering Script
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HOT → COLD Tier Veri Transferi (Airflow'da çalışabilir)

Nasıl Çalışır:
1. Iceberg metadata'dan eski partition'ları bulur (1 günden büyük)
2. İlgili dosyaları HOT'dan COLD'a taşır
3. Iceberg metadata güncellenmez (sadece fiziksel taşıma)
4. MinIO client (mc) ile çalışır

Kullanım:
  python3 scripts/tiering_job.py --age-days 1
  
Airflow'da:
  BashOperator(
      task_id='tier_data',
      bash_command='docker exec spark-master python3 /scripts/tiering_job.py --age-days 1'
  )
"""

import subprocess
import sys
from datetime import datetime, timedelta
import argparse
import json


class MinIOTieringManager:
    """MinIO HOT → COLD tier veri transfer yöneticisi"""
    
    def __init__(self, age_days=1, dry_run=False):
        """
        Args:
            age_days: Kaç günden eski data taşınacak (default: 1)
            dry_run: True ise sadece listele, taşıma (default: False)
        """
        self.age_days = age_days
        self.dry_run = dry_run
        self.hot_alias = "hot"
        self.cold_alias = "cold"
        self.hot_bucket = "iceberg-warehouse"
        self.cold_bucket = "iceberg-cold-tier"
        self.data_prefix = "db/transactions/data/"
        
    def run_mc_command(self, command):
        """MinIO client komutu çalıştır"""
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"❌ Hata: {e.stderr}")
            return None
    
    def get_cutoff_date(self):
        """Hangi tarihten önce taşınacak?"""
        cutoff = datetime.now() - timedelta(days=self.age_days)
        return cutoff.date()
    
    def list_hot_files(self):
        """HOT tier'daki tüm data dosyalarını listele"""
        print(f"📋 HOT tier dosyaları taranıyor...")
        
        command = f"mc ls --recursive --json {self.hot_alias}/{self.hot_bucket}/{self.data_prefix}"
        output = self.run_mc_command(command)
        
        if not output:
            return []
        
        files = []
        for line in output.strip().split('\n'):
            if not line:
                continue
            try:
                obj = json.loads(line)
                if obj.get('type') == 'file':
                    files.append({
                        'key': obj['key'],
                        'size': obj['size'],
                        'lastModified': obj['lastModified']
                    })
            except json.JSONDecodeError:
                continue
        
        return files
    
    def parse_partition_from_path(self, path):
        """Path'ten partition date çıkar
        
        Örnek: db/transactions/data/date=2025-10-03/file.parquet
        Return: datetime.date(2025, 10, 3)
        """
        try:
            if 'date=' in path:
                date_str = path.split('date=')[1].split('/')[0]
                return datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            pass
        return None
    
    def filter_old_files(self, files):
        """Eski dosyaları filtrele"""
        cutoff = self.get_cutoff_date()
        print(f"📅 Cutoff tarihi: {cutoff} (bu tarihten eski olanlar taşınacak)")
        
        old_files = []
        for file in files:
            partition_date = self.parse_partition_from_path(file['key'])
            if partition_date and partition_date < cutoff:
                old_files.append(file)
        
        return old_files
    
    def check_already_in_cold(self, file_key):
        """Dosya COLD'da var mı?"""
        # HOT: db/transactions/data/date=2025-10-03/file.parquet
        # COLD: data/date=2025-10-03/file.parquet (prefix farklı)
        
        cold_key = file_key.replace(self.data_prefix, 'data/')
        command = f"mc stat {self.cold_alias}/{self.cold_bucket}/{cold_key} 2>/dev/null"
        result = self.run_mc_command(command)
        return result is not None and len(result) > 0
    
    def copy_to_cold(self, file_key):
        """Dosyayı COLD'a kopyala"""
        hot_path = f"{self.hot_alias}/{self.hot_bucket}/{file_key}"
        
        # COLD'daki path (prefix değişir)
        cold_key = file_key.replace(self.data_prefix, 'data/')
        cold_path = f"{self.cold_alias}/{self.cold_bucket}/{cold_key}"
        
        print(f"   📤 Kopyalanıyor...")
        print(f"      FROM: {hot_path}")
        print(f"      TO:   {cold_path}")
        
        if self.dry_run:
            print("   🔸 DRY RUN - Gerçek kopyalama yapılmadı")
            return True
        
        # mc cp komutu
        command = f"mc cp {hot_path} {cold_path}"
        result = self.run_mc_command(command)
        
        if result:
            print(f"   ✅ Başarılı")
            return True
        else:
            print(f"   ❌ Başarısız")
            return False
    
    def run(self):
        """Ana tiering işlemi"""
        print("=" * 70)
        print("🔄 MinIO Manual Tiering Başlatıldı")
        print("=" * 70)
        print(f"⚙️  Ayarlar:")
        print(f"   • Age threshold: {self.age_days} gün")
        print(f"   • Dry run: {self.dry_run}")
        print(f"   • HOT: {self.hot_alias}/{self.hot_bucket}")
        print(f"   • COLD: {self.cold_alias}/{self.cold_bucket}")
        print()
        
        # 1. HOT dosyalarını listele
        all_files = self.list_hot_files()
        print(f"📊 Toplam {len(all_files)} dosya bulundu\n")
        
        if not all_files:
            print("ℹ️  Taşınacak dosya yok")
            return
        
        # 2. Eski dosyaları filtrele
        old_files = self.filter_old_files(all_files)
        print(f"🔍 {len(old_files)} eski dosya belirlendi\n")
        
        if not old_files:
            print("✅ Taşınması gereken dosya yok")
            return
        
        # 3. Her dosyayı taşı
        success_count = 0
        skip_count = 0
        fail_count = 0
        
        for i, file in enumerate(old_files, 1):
            partition = self.parse_partition_from_path(file['key'])
            size_mb = file['size'] / (1024 * 1024)
            
            print(f"\n[{i}/{len(old_files)}] 📁 Partition: {partition}")
            print(f"   📄 File: {file['key'].split('/')[-1]}")
            print(f"   💾 Size: {size_mb:.2f} MB")
            
            # COLD'da var mı kontrol et
            if self.check_already_in_cold(file['key']):
                print(f"   ⏭️  Zaten COLD'da var - atlanıyor")
                skip_count += 1
                continue
            
            # COLD'a kopyala
            if self.copy_to_cold(file['key']):
                success_count += 1
            else:
                fail_count += 1
        
        # 4. Özet
        print("\n" + "=" * 70)
        print("📊 ÖZET")
        print("=" * 70)
        print(f"✅ Başarılı: {success_count}")
        print(f"⏭️  Atlandı:  {skip_count}")
        print(f"❌ Başarısız: {fail_count}")
        print(f"📦 Toplam:   {len(old_files)}")
        print()
        
        if self.dry_run:
            print("🔸 DRY RUN modu - gerçek değişiklik yapılmadı")
            print("   Çalıştırmak için: --no-dry-run ekleyin")
        else:
            print("✅ Tiering tamamlandı!")
        
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="MinIO HOT → COLD tier veri transfer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  # 1 günden eski datayı taşı (dry-run)
  python3 tiering_job.py --age-days 1
  
  # Gerçekten taşı
  python3 tiering_job.py --age-days 1 --no-dry-run
  
  # 2 günden eski datayı taşı
  python3 tiering_job.py --age-days 2 --no-dry-run
        """
    )
    
    parser.add_argument(
        '--age-days',
        type=int,
        default=1,
        help='Kaç günden eski data taşınacak (default: 1)'
    )
    
    parser.add_argument(
        '--no-dry-run',
        action='store_true',
        help='Gerçek transfer yap (default: dry-run)'
    )
    
    args = parser.parse_args()
    
    # Tiering manager oluştur ve çalıştır
    manager = MinIOTieringManager(
        age_days=args.age_days,
        dry_run=not args.no_dry_run
    )
    
    manager.run()


if __name__ == "__main__":
    main()

