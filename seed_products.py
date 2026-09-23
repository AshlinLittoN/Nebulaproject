from db import get_conn

products = [
    ('Amul Gold Milk 500ml','AMUL-MILK-500ML','ml',0,28.0,32.0,5.0,'0401',20,100),
    ('Britannia Marie Biscuit 200g','BRIT-MARIE-200G','packet',0,18.0,22.0,18.0,'1905',20,60),
    ('Colgate Toothpaste 100g','COLG-PASTE-100G','packet',0,55.0,70.0,18.0,'3306',15,40),
    ('Dettol Soap 75g','DETT-SOAP-75G','piece',0,38.0,48.0,18.0,'3401',20,50),
    ('Vim Dishwash Bar 200g','VIM-DISH-200G','piece',0,18.0,24.0,18.0,'3402',15,40),
    ('Lifebuoy Soap 100g','LIFE-SOAP-100G','piece',0,28.0,36.0,18.0,'3401',20,50),
    ('Tata Tea Premium 250g','TATA-TEA-250G','packet',0,95.0,120.0,5.0,'0902',15,30),
    ('Nescafe Classic 50g','NESC-CLAS-50G','packet',0,195.0,245.0,18.0,'2101',10,20),
    ('Horlicks 500g','HORL-500G','packet',0,210.0,265.0,18.0,'1901',10,20),
    ('Amul Cheese Slice 200g','AMUL-CHES-200G','packet',0,95.0,120.0,12.0,'0406',10,25),
    ('Kissan Jam 200g','KISS-JAM-200G','packet',0,65.0,85.0,12.0,'2007',10,25),
    ('Maggi Masala 50g','MAGG-MASA-50G','packet',0,8.0,10.0,18.0,'2103',30,80),
    ('MDH Garam Masala 100g','MDH-GARAM-100G','packet',0,55.0,70.0,5.0,'0910',15,30),
    ('Everest Chilli Powder 100g','EVER-CHIL-100G','packet',0,42.0,55.0,5.0,'0904',15,30),
    ('Saffola Gold Oil 1L','SAFF-OIL-1L','litre',0,145.0,175.0,5.0,'1512',10,25),
    ('Amul Ghee 500ml','AMUL-GHEE-500ML','ml',0,270.0,320.0,12.0,'0405',10,20),
    ('Haldiram Bhujia 200g','HALD-BHUJ-200G','packet',0,55.0,70.0,12.0,'2106',15,30),
    ('Kurkure Masala 90g','KURK-MASA-90G','packet',0,18.0,22.0,12.0,'1905',20,50),
    ('Pepsi 600ml','PEPS-600ML','ml',0,28.0,35.0,28.0,'2202',20,48),
    ('Coca Cola 600ml','COCA-600ML','ml',0,28.0,35.0,28.0,'2202',20,48),
    ('Sprite 600ml','SPRI-600ML','ml',0,28.0,35.0,28.0,'2202',20,48),
    ('Bisleri Water 1L','BISL-WAT-1L','litre',0,12.0,20.0,18.0,'2201',30,60),
    ('Parle Frooti 200ml','PARL-FROOT-200ML','ml',0,12.0,15.0,12.0,'2009',20,48),
    ('Wheel Detergent 500g','WHEE-DET-500G','packet',0,38.0,50.0,18.0,'3402',15,40),
    ('Harpic Toilet Cleaner 500ml','HARP-TOIL-500ML','ml',0,85.0,110.0,18.0,'3808',10,20),
    ('Good Knight Coil','GOOD-COIL','packet',0,28.0,35.0,12.0,'3808',15,30),
    ('Wheat (loose)','WHEAT-LOOSE','kg',1,28.0,35.0,0.0,'1001',10,40),
    ('Maida (loose)','MAIDA-LOOSE','kg',1,30.0,38.0,0.0,'1101',10,30),
    ('Poha (loose)','POHA-LOOSE','kg',1,45.0,55.0,0.0,'1104',10,25),
    ('Chana Dal (loose)','CHANA-LOOSE','kg',1,75.0,90.0,0.0,'0713',10,25),
]

conn = get_conn()
inserted = 0
skipped = 0
for p in products:
    existing = conn.execute('SELECT id FROM products WHERE sku=?', (p[1],)).fetchone()
    if existing:
        skipped += 1
        continue
    conn.execute(
        'INSERT INTO products (name,sku,unit,is_loose,cost_price,mrp,gst_rate,hsn_code,reorder_level,quantity) VALUES (?,?,?,?,?,?,?,?,?,?)',
        p
    )
    inserted += 1
conn.commit()
total = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
conn.close()
print(f'Inserted: {inserted}, Skipped: {skipped}, Total: {total}')
