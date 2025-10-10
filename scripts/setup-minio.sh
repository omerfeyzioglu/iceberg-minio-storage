#!/bin/bash
# MinIO Setup Script
# HOT ve COLD tier kurulumu + ILM yapılandırması

set -e

echo "🚀 MinIO Multi-Tier Setup Başlatılıyor..."
echo "=========================================="

# Renk kodları
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# MinIO servislerinin hazır olmasını bekle
echo -e "\n${YELLOW}⏳ MinIO servislerinin başlaması bekleniyor...${NC}"
sleep 10

# HOT TIER Alias
echo -e "\n${BLUE}📌 HOT TIER MinIO yapılandırılıyor...${NC}"
mc alias set hot http://minio-hot:9000 minioadmin minioadmin
echo -e "${GREEN}✅ HOT tier alias eklendi${NC}"

# COLD TIER Alias
echo -e "\n${BLUE}📌 COLD TIER MinIO yapılandırılıyor...${NC}"
mc alias set cold http://minio-cold:9000 minioadmin minioadmin
echo -e "${GREEN}✅ COLD tier alias eklendi${NC}"

# HOT TIER Bucket'ları oluştur
echo -e "\n${BLUE}🪣 HOT TIER Bucket'ları oluşturuluyor...${NC}"

# Iceberg metadata bucket
if mc ls hot/iceberg-metadata 2>/dev/null; then
    echo "   iceberg-metadata bucket mevcut"
else
    mc mb hot/iceberg-metadata
    echo -e "${GREEN}   ✅ iceberg-metadata bucket oluşturuldu${NC}"
fi

# Iceberg warehouse bucket (versioning aktif)
if mc ls hot/iceberg-warehouse 2>/dev/null; then
    echo "   iceberg-warehouse bucket mevcut"
else
    mc mb hot/iceberg-warehouse
    mc version enable hot/iceberg-warehouse
    echo -e "${GREEN}   ✅ iceberg-warehouse bucket oluşturuldu (versioning aktif)${NC}"
fi

# COLD TIER Bucket oluştur
echo -e "\n${BLUE}🧊 COLD TIER Bucket oluşturuluyor...${NC}"
if mc ls cold/iceberg-cold-tier 2>/dev/null; then
    echo "   iceberg-cold-tier bucket mevcut"
else
    mc mb cold/iceberg-cold-tier
    echo -e "${GREEN}   ✅ iceberg-cold-tier bucket oluşturuldu${NC}"
fi

# HOT MinIO'ya COLD tier'ı remote tier olarak ekle
echo -e "\n${BLUE}🔗 COLD tier, HOT MinIO'ya remote tier olarak ekleniyor...${NC}"

# Önce mevcut tier'ı kontrol et ve varsa sil
if mc admin tier ls hot | grep -q "COLDTIER"; then
    echo "   COLDTIER mevcut, yeniden yapılandırılıyor..."
    mc admin tier rm hot COLDTIER 2>/dev/null || true
fi

# Remote tier ekle
mc admin tier add minio hot COLDTIER \
    --endpoint http://minio-cold:9000 \
    --access-key minioadmin \
    --secret-key minioadmin \
    --bucket iceberg-cold-tier \
    --prefix "" \
    --region ""

echo -e "${GREEN}✅ COLDTIER remote tier eklendi${NC}"

# Tier'ları listele
echo -e "\n${BLUE}📋 Yapılandırılmış Tier'lar:${NC}"
mc admin tier ls hot

# ILM Policy - data/ prefix için 1 gün sonra COLD tier'a taşı
echo -e "\n${BLUE}⚙️ ILM Lifecycle Policy yapılandırılıyor...${NC}"

# ILM policy JSON dosyası oluştur
cat > /tmp/ilm-policy.json <<EOF
{
    "Rules": [
        {
            "ID": "TransitionToCold",
            "Status": "Enabled",
            "Filter": {
                "Prefix": "data/"
            },
            "Transition": {
                "Days": 1,
                "StorageClass": "COLDTIER"
            }
        }
    ]
}
EOF

# ILM policy'yi uygula
mc ilm import hot/iceberg-warehouse < /tmp/ilm-policy.json
echo -e "${GREEN}✅ ILM policy uygulandı (data/ prefix, 1 gün sonra COLD tier'a)${NC}"

# Policy'yi göster
echo -e "\n${BLUE}📋 Aktif ILM Policy:${NC}"
mc ilm ls hot/iceberg-warehouse

# Test için örnek dosya oluştur (opsiyonel)
echo -e "\n${BLUE}🧪 Test dosyası oluşturuluyor...${NC}"
echo "Test data for tiering" > /tmp/test.txt
mc cp /tmp/test.txt hot/iceberg-warehouse/data/test.txt
echo -e "${GREEN}✅ Test dosyası yüklendi (hot/iceberg-warehouse/data/test.txt)${NC}"

# Özet bilgi
echo -e "\n${GREEN}=========================================="
echo "✨ MinIO Multi-Tier Kurulumu Tamamlandı!"
echo "==========================================${NC}"
echo -e "\n${BLUE}📊 Yapılandırma Özeti:${NC}"
echo "  🔥 HOT TIER (Primary):"
echo "     - Endpoint: http://minio-hot:9000"
echo "     - Console: http://localhost:9001"
echo "     - Buckets: iceberg-metadata, iceberg-warehouse"
echo ""
echo "  🧊 COLD TIER (Remote):"
echo "     - Endpoint: http://minio-cold:9000"
echo "     - Console: http://localhost:9101"
echo "     - Bucket: iceberg-cold-tier"
echo ""
echo "  ⚙️ ILM Policy:"
echo "     - Prefix: data/"
echo "     - Transition: 1 gün sonra COLDTIER'a"
echo "     - Compression: Iceberg tarafından ZSTD ile yapılacak"
echo ""
echo -e "${YELLOW}💡 İpucu:${NC}"
echo "  - Veri ingestion için: docker exec -it spark-master python /scripts/ingest_data.py"
echo "  - Compaction için: docker exec -it spark-master python /scripts/compaction_job.py"
echo "  - MinIO Console (HOT): http://localhost:9001"
echo "  - MinIO Console (COLD): http://localhost:9101"
echo "  - Spark UI: http://localhost:8080"
echo ""

# Temizlik
rm -f /tmp/test.txt /tmp/ilm-policy.json
