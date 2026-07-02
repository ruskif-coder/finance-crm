-- sync_edo_contracts.sql
-- Synkronizatsiya dannykh iz Diadoc s tablitsey contracts.
-- 1. Dobavlyaet kolonki edo_status i edo_signed_at (esli ikh net).
-- 2. UPDATE po INN + nomer dogovora (tochnoe sovpadenie).
-- 3. UPDATE po INN dlya pustykh zapisey (contract_number IS NULL / '') — tolko esli odna takaya zapis.
-- document_link ne pereterayet uzhe zapolnennuyu ssylku.

BEGIN;

-- 1. Migratsiya: novyye kolonki
ALTER TABLE contracts
  ADD COLUMN IF NOT EXISTS edo_status     VARCHAR,
  ADD COLUMN IF NOT EXISTS edo_signed_at  TIMESTAMP;

-- 2. Vremennyy staging
CREATE TEMP TABLE edo_stage (
  inn        VARCHAR,
  num        VARCHAR,
  date_doc   DATE,
  link       TEXT,
  status     VARCHAR,
  signed_at  TIMESTAMP
);

INSERT INTO edo_stage (inn, num, date_doc, link, status, signed_at) VALUES
  ('7733320702','1-12/21DSP','2021-12-08','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=e27c54b7-cf15-45b0-87f8-c85d687fc63e&documentId=22bbbe04-5533-4d09-8d28-40d37caa4b4e','Подписан контрагентом','2021-12-10 10:35:07'),
  ('7707444765','ПМ-СЛ 05-12-21','2021-12-05','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=65cc02da-121b-4970-b1d4-5fc4bc116e39&documentId=f9ce796a-06ef-4544-8309-31f4c58e4fcd','Подписан контрагентом','2022-01-19 16:29:52'),
  ('7715783088','PM-01-08-23','2023-08-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=eb572781-78ca-40bc-a4cb-95f8da3073ba&documentId=458c0be0-31c4-4535-84c8-b35ff1b4b0c9','Подписан контрагентом','2023-08-01 17:00:20'),
  ('7720410518','РМ-13-07-23','2023-07-13','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=5835bf77-dc08-4345-9df0-6a8aaaaf0175&documentId=eb542595-567d-4512-89e1-2ac740ea0ffd','Подписан контрагентом','2023-08-08 14:22:04'),
  ('9701087285','PM-01/08/23','2023-08-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=254bba95-5429-4286-84ab-929d561aa2d5&documentId=599d849b-ce58-4500-840e-72d1ec2816b8','Подписан контрагентом','2023-08-24 16:00:07'),
  ('7710899410','РМ-01-06-23','2023-06-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=9b7faa53-9630-49f2-9d01-f1477b37d29a&documentId=ce40482b-58b3-4bd1-bd72-a5acfb0efd4a','Подписан контрагентом','2023-08-22 16:52:08'),
  ('3917032714','PM-21-08-23','2023-08-21','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=4ac0d251-43fa-414a-a921-7ee6a0601f01&documentId=7a48980e-3df6-461a-9351-aa2a17a0bdea','Подписан контрагентом','2023-09-06 15:31:16'),
  ('631227336588','01/Р/В/23','2023-09-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=fd1697ab-ecea-4f65-bff0-1828b59c9aea&documentId=8d249d52-300d-4c26-adb7-28454e39c175','Подписан контрагентом','2023-09-17 21:26:32'),
  ('7751155145','PM-15-09-23','2023-09-15','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=59208b1c-2c39-4952-928c-2276f9497ddc&documentId=aa081016-47fd-40c2-b2b4-2d1c1a2d9960','Подписан контрагентом','2023-09-15 12:04:15'),
  ('7731575688','СБ-26-10-23','2023-10-26','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=92e7410f-cd3d-4e01-9dfb-1b642bb8214a&documentId=9ead572f-f77f-4c8b-89af-dc2cf5b000d2','Подписан контрагентом','2023-11-29 10:25:17'),
  ('7743068844','PM-11-11-23','2023-11-11','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=a5362b9a-0020-48fb-a082-ebd03fdcf5ec&documentId=3a9ace80-f383-41e2-ba60-b0e75e4bcd4c','Подписан контрагентом','2023-11-24 14:50:24'),
  ('7706426788','PM-16-11-2023','2023-11-16','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=bf92a1be-1f63-4be2-9945-a969aa24c96f&documentId=dfd2ef41-08df-43d7-8dc4-240574123477','Подписан контрагентом','2023-11-23 11:39:17'),
  ('9731048741','РМ-30-11-2023','2023-11-30','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=51710700-73c7-4329-a92d-1a6899ed522e&documentId=8b40f763-20d5-4419-82b2-ede37f90c8bf','Подписан контрагентом','2023-12-01 12:27:03'),
  ('7706448809','Web – ПМ/ГЛ2023','2023-11-14','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=3bcb6b69-1171-4ac7-a2bf-4ec24a87bee8&documentId=eb4102d6-51ba-42d6-9a3a-6a384b6c7703','Подписан контрагентом','2024-01-15 17:10:08'),
  ('9718224170','РМ 24-11-2023','2023-11-24','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=1c6ec1d2-32c9-4255-a787-99f4781ff27e&documentId=1e1b3ca3-3c3e-40de-be78-8eda419d5797','Подписан контрагентом','2023-12-07 14:42:21'),
  ('7725560073','РМ 01-12-2023','2023-12-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=14b18cde-5880-4a37-b9d8-e40f2b08ee59&documentId=df63a524-8bef-4358-89db-26cef909845a','Подписан контрагентом','2023-12-05 17:22:25'),
  ('7701974131','PM-28/11-23','2023-11-28','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=2eb5ff0e-565c-4a13-849b-dd4a35ebdb77&documentId=23a43e55-010f-46c8-9212-b5bf5f91a0fd','Подписан контрагентом','2023-12-08 11:29:35'),
  ('7718258802','PM 12-12-2023','2023-12-12','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=64ccbb58-1ff9-403d-80ed-ca9d47e024fa&documentId=a8adf135-5f59-4e2d-b7cb-bbeb51d71e2c','Подписан контрагентом','2023-12-18 14:30:42'),
  ('7724890784','PM-11-01-2024','2024-01-11','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=60f220df-dbf4-46e0-ae96-22b71e4c0589&documentId=90d9977b-ee4b-48d7-bb1e-bacdeadff2c9','Подписан контрагентом','2024-01-30 10:09:34'),
  ('7703388936','PM-01/02-24','2024-02-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=1e5aafed-ee47-410b-97d9-537bce0309ef&documentId=2a20558d-bae6-462c-afc0-07290fc237fe','Подписан контрагентом','2024-03-04 11:05:59'),
  ('6662126172','PM-28-02-24','2024-02-28','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=e6f09b4d-485d-45a9-9dab-eb94f0346033&documentId=6ce05c2f-9d3a-40bd-87cc-e24aff391c05','Подписан контрагентом','2024-03-25 09:56:36'),
  ('7710703730','УК-ПМ-1103','2024-03-11','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=7f93d0f6-33fb-4e27-bc70-d5be6e7da4f3&documentId=0469063b-5529-4dfd-ac08-62c793308174','Подписан контрагентом','2024-04-08 17:57:44'),
  ('7701974131','СК-01/01-24','2024-01-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=92131bd6-1f69-4b19-948d-44e45c24897c&documentId=3ae14e8b-980e-46e7-ba0d-3070613db60a','Требуется аннулирование','2024-05-07 14:02:48'),
  ('7734440400','РМ-01-04-24','2024-04-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=eccbe9aa-60ac-4a70-b315-1d071c18308d&documentId=7999f4e5-5e81-4a2e-a92f-f881eb5eab32','Подписан контрагентом','2024-04-27 12:10:33'),
  ('7734490680','РМ-01-04-24','2024-04-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=ac6e1266-f9ac-4bf3-9dcf-52e2a64b1739&documentId=30825407-6900-4e66-b0c7-cd5e3a9918d0','Подписан контрагентом','2024-05-30 11:15:49'),
  ('7733363512','PM-14-05-24','2024-05-14','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=5e6ea2bf-0d96-43f2-aabf-ae1167efa0f3&documentId=6ef9ec8e-bb1e-4d05-bf26-ae3babb75dce','Подписан контрагентом','2024-05-17 15:50:57'),
  ('7802927160','ДГ 15-05-24','2024-05-15','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=c82126cc-fc86-408e-aa02-16086b812eb5&documentId=ad87c558-4fcd-4079-a732-e16d8f95bc64','Подписан контрагентом','2024-06-04 11:20:32'),
  ('9701257829','PM-30-04-24','2024-04-30','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=84e7b767-2b37-43ac-979b-793798de00d4&documentId=986fbd2e-d9a3-4955-8d57-c7ea56fb4263','Подписан контрагентом','2024-06-07 15:39:33'),
  ('5010031832','PM-03-06-2024','2024-06-03','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=33bc2487-07b6-462f-9abb-480b8da40ecc&documentId=00ffeba2-6bda-4c70-a57e-946c7a81c847','Подписан контрагентом','2024-07-12 09:30:00'),
  ('5018112138','PM-09-07-2024','2024-07-09','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=7726336b-b7bd-4f20-b00d-2e73fe566db3&documentId=2159515d-27bf-4e13-8dc7-27f74c22644a','Подписан контрагентом','2024-07-15 11:37:54'),
  ('7736602705','PM-20-08-2024','2024-08-20','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=d6940261-4719-4ad9-be6c-add216618318&documentId=c60a8758-f593-4847-87c8-5180e62fa9d0','Подписан контрагентом','2024-08-21 16:03:49'),
  ('7723828649','PM-23-08-2024','2024-08-23','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=ed554675-659f-4023-8c01-1b3ada9c7a1b&documentId=131bf08a-9ca6-4a41-8289-dd6e7b4af45d','Подписан контрагентом','2024-08-30 11:59:24'),
  ('7707408358','АС-АР-42','2024-09-02','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=fc20688c-f194-4949-9b77-6137979d8d25&documentId=b649ff7d-57a8-4985-b4dc-ce244f982adc','Подписан контрагентом','2024-09-16 11:54:27'),
  ('4706049566','19092024-1','2024-09-19','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=22c406dc-d5ed-49b5-9220-181257aee867&documentId=183c837c-ed4e-4e95-9cda-b9b30c26b2c6','Подписан контрагентом','2024-09-23 09:48:22'),
  ('5024223277','РМ 13-09-2024','2024-09-13','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=38de44e3-5852-4ab2-ae21-2085e3bd4a99&documentId=a515ee62-f5ce-4e39-9559-5563212dc1e1','Подписан контрагентом','2024-09-23 11:12:09'),
  ('2724155394','РМ-01-10-24','2024-10-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=58ec9864-6559-4cd4-860a-5de0f563288f&documentId=fec06a81-fa04-43d4-a33a-0202ddacb310','Подписан контрагентом','2024-10-08 04:21:14'),
  ('7713472626','PM-07102024','2024-10-07','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=86338799-18a0-4c68-8a9c-c51951cd3f79&documentId=afe0b3cd-7a12-4c5f-9abe-59a126ad01cc','Подписан контрагентом','2024-10-10 14:37:48'),
  ('9717094351','РМ-30-08-2024','2024-08-30','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=7bc6348e-53ce-44b4-8de7-ba6176ab38ea&documentId=3dca3839-40a4-4fc3-8cb8-0524eff42de6','Подписан контрагентом','2024-10-15 14:00:05'),
  ('2721065128','РМ-08-10-24','2024-10-08','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=76ed0a79-b6d8-4fce-8df4-56932cd774fb&documentId=d8aecf0d-be3f-49c0-a762-6a7fa5fab25e','Подписан контрагентом','2024-10-16 09:53:05'),
  ('7701714503','PM-08-10-24','2024-10-08','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=194784c3-9da0-4f33-8f6d-a2ca0273d3ba&documentId=4fe7bad4-1479-477e-aa6b-2f60536736ef','Подписан контрагентом','2024-10-28 11:18:27'),
  ('7106040119','РМ 13-11-24','2024-11-13','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=4e52d01f-fbb8-4a39-b63a-114ac4fab929&documentId=0b4110e6-a6ed-45d6-8b11-61e47da981cc','Подписан контрагентом','2024-11-18 10:59:42'),
  ('263602273075','АП-26-11-2024','2024-11-26','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=3096212a-e2e5-4a31-8264-c47956c44103&documentId=45125b32-ebb5-4789-896e-153c0adec0a2','Подписан контрагентом','2024-11-26 15:09:17'),
  ('263602273075','АГ-26-11-2024','2024-11-26','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=3096212a-e2e5-4a31-8264-c47956c44103&documentId=eac948e8-2ac0-4203-8eea-1a11043ca2c2','Подписан контрагентом','2024-11-26 15:09:17'),
  ('3525462949','АП 10-12-2024','2024-12-10','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=13091bf9-8f8b-449b-ae42-3d6c24c1154b&documentId=0b207d68-d1f8-4ac2-ab2d-f091bf929367','Подписан контрагентом','2024-12-13 08:52:04'),
  ('7731347547','PM-29-11-2024','2024-11-29','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=d020a455-d0fc-4984-b516-229d50f61357&documentId=46c1521a-fa02-43b8-9489-e420aa64f1c9','Подписан контрагентом','2024-12-19 17:27:58'),
  ('7726548343','PM-21-11-2024','2024-11-21','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=8101902b-4db0-4f01-b43d-f3988bf94b2a&documentId=062f7096-01f0-40ed-8905-6ef74b62f580','Подписан контрагентом','2024-12-26 13:24:54'),
  ('7728716402','PM-23-12-24','2024-12-23','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=2be0ff65-3ced-4f5d-84b7-83de7b1a23d5&documentId=94c7a25b-683b-4197-80d0-c42275ad3304','Подписан контрагентом','2024-12-26 16:35:07'),
  ('7724211288','РМ-01-10-24','2024-10-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=fb65079d-5c21-4624-bbf4-b44a922019ea&documentId=8c0f36ec-00cf-47e0-b0e9-8eff2fff06bc','Подписан контрагентом','2025-01-19 23:39:41'),
  ('7706132442','28-12-2024','2024-12-28','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=8465c367-68df-45a3-bebd-215f920c0a41&documentId=45ee11a6-72e8-462a-ba85-60da32b483d2','Подписан контрагентом','2025-01-13 18:32:31'),
  ('9701257829','ИН-02-09-24','2024-09-02','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=ceb3c8fc-2766-4668-aa7a-ea54f6358372&documentId=35028e6b-0c67-4509-914b-38982687ed0b','Подписан контрагентом','2025-01-15 12:56:26'),
  ('5903158326','РА-14-01-25','2025-01-14','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=1e339916-2468-41b6-aaad-7b822cb2bf37&documentId=f9a2a280-6b3b-421a-8a77-ec5da2a01e47','Подписан контрагентом','2025-02-05 14:30:36'),
  ('7715661354','PM-31-01-25','2025-01-31','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=9ecbe0fa-bd57-43b5-9cac-9b39ebba5622&documentId=d6d78b23-5c0c-484a-874d-9be79f770079','Подписан контрагентом','2025-02-17 17:56:02'),
  ('7709855129','PM-03-02-25','2025-02-03','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=cdd701b0-6b8e-40d6-a402-e8da688c8d8f&documentId=03ace717-08f8-4f3f-94b4-26873759d1a0','Подписан контрагентом','2025-02-07 10:59:39'),
  ('3665823962','АГ-12-02-25','2025-02-12','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=8873fb81-0cfc-4e0e-8547-26244fc99bc5&documentId=47af0761-a1c4-419d-8c41-5365f6e5019b','Подписан контрагентом','2025-02-27 17:42:18'),
  ('3665823962','РА-12-02-25','2025-02-12','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=8873fb81-0cfc-4e0e-8547-26244fc99bc5&documentId=eae4a776-0ce6-4ed5-b242-7199a1a0d9d0','Подписан контрагентом','2025-02-27 17:42:11'),
  ('0571018796','РА-18-02-25','2025-02-18','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=8c155a0a-3eed-449b-872e-e7e0dd219e0f&documentId=c388eb3a-4aa4-44ea-b47e-425cf73bf989','Подписан контрагентом','2025-02-28 17:12:57'),
  ('0571018796','АГ-18-02-25','2025-02-18','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=8c155a0a-3eed-449b-872e-e7e0dd219e0f&documentId=27f45069-dc60-410e-aa60-e67f8bbffcba','Подписан контрагентом','2025-02-28 17:12:57'),
  ('0571008484','АГ-17-02-25','2025-02-17','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=d5b941e4-a9ba-4329-a6b5-1ed4811eb4a3&documentId=a8b62571-71df-4a48-a1da-0a44baca3dec','Подписан контрагентом','2025-02-28 16:56:14'),
  ('0571008484','РА-17-02-25','2025-02-17','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=d5b941e4-a9ba-4329-a6b5-1ed4811eb4a3&documentId=3630bdd8-6db8-4edd-aa7d-5a689f194931','Подписан контрагентом','2025-02-28 16:56:13'),
  ('2721065128','АГ-08-10-24','2024-10-08','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=940241dc-01aa-49c9-b528-13644c2e6fd3&documentId=d015a214-cc7b-4093-b18b-fa186878e1f5','Подписан контрагентом','2025-03-24 04:23:30'),
  ('2724155394','АГ-01-10-24','2024-10-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=c1615621-e375-4a52-a6df-270c91fee545&documentId=dae6cddf-64b9-48d2-b0aa-b5a72e7625f0','Подписан контрагентом','2025-03-24 04:23:30'),
  ('7714707736','010225-1','2025-02-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=56d722c8-3292-4ec1-9e85-e5960ba7802a&documentId=b74da79d-b95c-4660-96f5-2ba92f495748','Подписан контрагентом','2025-03-19 17:55:18'),
  ('2724214018','РА-04-03-25','2025-03-04','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=459661c9-d0b3-425a-90f0-e85f1e492eaf&documentId=d4b9574c-0c16-4e8e-93e6-ccf9b7522d0e','Подписан контрагентом','2025-03-24 04:23:52'),
  ('2724214018','АГ-04-03-25','2025-03-04','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=459661c9-d0b3-425a-90f0-e85f1e492eaf&documentId=983e3f90-57cf-4c20-a9b4-c3aab918ac9b','Подписан контрагентом','2025-03-24 04:23:52'),
  ('7743237860','РМ-01-04-25','2025-04-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=989e1faf-21db-4fc2-8328-596bc1d63f08&documentId=1b8d5d4f-0344-496f-91eb-bbe869beff27','Подписан контрагентом','2025-03-26 13:07:32'),
  ('7706811620','PM-05-05-25','2025-05-05','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=3f5e1111-f342-419c-a7d4-5058e321ad38&documentId=95c72e3f-2639-4dfd-9b85-e7b341eb54d2','Подписан контрагентом','2025-05-14 16:55:26'),
  ('3102202594','АГ-11-04-25','2025-04-11','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=5c7623ad-0956-41af-9fa6-614b78527cdd&documentId=98522c2d-efad-4e8c-85d3-3b368cd27190','Подписан контрагентом','2025-05-30 14:28:47'),
  ('3102202594','РА №-11-04-25','2025-04-11','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=5c7623ad-0956-41af-9fa6-614b78527cdd&documentId=3deb699e-c809-4f63-948e-af1741eebb21','Подписан контрагентом','2025-05-30 14:28:47'),
  ('7729578280','СП-02-06-25','2025-06-02','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=1a62cb1d-4c52-4490-8626-e729c7e30c80&documentId=a1a68b9c-050e-405d-8543-eba7ce7a8b14','Подписан контрагентом','2025-06-24 18:34:05'),
  ('5257118934','ИНД-01-07-2025\1','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=c86f6d86-70c7-4b5e-bb8c-b97d18e0f67e&documentId=f1244514-0b5a-4f85-81fb-f0c1f3f5408f','Подписан контрагентом','2025-07-09 15:18:39'),
  ('5260409563','ИНД-01-07-2025\17','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=9e705627-3491-41d9-8909-53d799cecfb7&documentId=a7453b4c-0909-4ca7-a6f1-2802fad6131c','Подписан контрагентом','2025-07-09 15:18:57'),
  ('5262296509','ИНД-01-07-2025\16','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=c741f5f0-44d8-450a-830e-78f5b5e4e67a&documentId=f0619dde-88b5-4aa4-973d-05625326864d','Подписан контрагентом','2025-07-09 15:18:57'),
  ('5257096230','ИНД-01-07-2025\15','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=2d9c09d3-409d-4773-b442-b542a5e20388&documentId=909a1088-a15b-4112-95e8-95a4f32b69e7','Подписан контрагентом','2025-07-09 15:19:07'),
  ('5260406072','ИНД-01-07-2025\14','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=5b2b80b2-5f9d-449c-a58b-ab569181aae5&documentId=bfa616bc-673c-43dc-bc93-d67617a0a96f','Подписан контрагентом','2025-07-09 15:19:08'),
  ('5257110237','ИНД-01-07-2025\13','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=288d2bb2-0c2c-47e5-a60c-6b29cb5070f1&documentId=ac4ed2da-a003-4a15-b1d6-90fb2a1e99cd','Подписан контрагентом','2025-07-10 10:57:30'),
  ('5260403787','ИНД-01-07-2025\12','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=88a64116-689f-4cc6-9d8a-006febe3c71b&documentId=792e083d-dba7-486a-a784-cce60c90e446','Подписан контрагентом','2025-07-09 16:35:59'),
  ('6726022848','ИНД-01-07-2025\11','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=cd3ca3cb-93be-406c-b0a9-260e935de96a&documentId=a23a8c01-58e7-4911-ba87-b1c343cc6ef9','Подписан контрагентом','2025-07-09 15:14:18'),
  ('4029049486','ИНД-01-07-2025\10','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=3baafdfe-3440-4882-9e6b-d3b0a5dd70ff&documentId=9ee5c1d5-a7ae-45e4-90d7-58dc5ac6b7ff','Подписан контрагентом','2025-07-09 17:44:48'),
  ('6230121836','ИНД-01-07-2025\9','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=24c9a848-fae6-453d-9aba-3509d61b6402&documentId=4a9dfddb-caa8-4673-a6df-1564e9cb258c','Подписан контрагентом','2025-07-09 15:16:17'),
  ('5257133298','ИНД-01-07-2025\8','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=b802428e-72ca-4d46-a801-28a96245e0e0&documentId=2eaf44a3-eac7-4171-a1ba-804537b77279','Подписан контрагентом','2025-07-09 15:15:44'),
  ('7100016007','ИНД-01-07-2025\7','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=f1a2ece0-e9a2-4678-9a0a-42373f84e23d&documentId=17fe98bf-f347-4ddb-b9f3-796a278b3ad1','Подписан контрагентом','2025-07-09 15:16:13'),
  ('5262287127','ИНД-01-07-2025\6','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=9176ff15-aea8-4efc-bd7a-319b70cc337e&documentId=96e46de6-f537-4eac-adf7-455bb391b0b1','Подписан контрагентом','2025-07-09 15:23:06'),
  ('5260398400','ИНД-01-07-2025\5','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=6f81aaa5-41cd-459f-a790-e9e60885c404&documentId=938cbceb-ed56-4123-89ad-805fe794430f','Подписан контрагентом','2025-07-09 17:45:10'),
  ('5262286941','ИНД-01-07-2025\4','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=4e1cc3d5-5abc-4e3a-a716-6522336cabe0&documentId=17efb09f-88fd-4f59-94cb-ac1ec67131ae','Подписан контрагентом','2025-07-09 15:19:38'),
  ('3662299109','ИНД-01-07-2025\3','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=fa661c93-833b-4061-88ec-bdd6f7ffa1d2&documentId=65c3514a-8083-40e7-b5be-5e989ecb282a','Подписан контрагентом','2025-07-09 15:19:26'),
  ('5262295174','ИНД-01-07-2025\2','2025-07-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=8ed02377-ebce-4e4a-9361-247031dec088&documentId=8340e974-f54d-4ac9-a223-4530071760c7','Подписан контрагентом','2025-07-09 15:18:12'),
  ('5074094524','АТ-10-07-25','2025-07-10','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=e4805f09-5bc5-4f08-9b06-4df84c8eb9e2&documentId=6a923df0-f6a4-4219-aedf-20ac48a55608','Подписан контрагентом','2025-07-10 17:02:07'),
  ('5262333239','РА-01-08-25/1','2025-08-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=36a9da74-e8c0-4000-bb81-21a56d89ea28&documentId=e0414873-65ca-449f-b929-ac944dc56853','Подписан контрагентом','2025-07-30 18:21:30'),
  ('5074094524','АТ-01-08-25/1','2025-08-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=c6ea6c12-22f7-4225-8690-23d90bed841b&documentId=4090962f-e0ed-4cc0-9566-867f589f5a91','Подписан контрагентом','2025-08-04 10:56:46'),
  ('5074094524','АТ-01-08-25/2','2025-08-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=c6ea6c12-22f7-4225-8690-23d90bed841b&documentId=f80271c8-9eb8-4163-a01c-d1274e786f21','Подписан контрагентом','2025-08-04 10:58:00'),
  ('773472005001','АГ-04-08-25','2025-08-04','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=de72880d-8b96-4037-8f2e-290987c21ef6&documentId=91ec5d67-5633-417e-aff7-fc03ff3700a7','Подписан контрагентом','2025-08-11 12:31:36'),
  ('7731437293','РМ-10-09-25','2025-09-10','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=4283f982-feab-46c6-a8ff-9af8d9adef45&documentId=36225da2-6ba0-4172-b134-6df8315c2347','Подписан контрагентом','2025-09-25 15:22:46'),
  ('3849058140','РА-23-09-25','2025-09-23','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=34498674-1888-4815-a1db-e80c97c5b22f&documentId=fecd62a0-e94b-43b0-b177-49ae6b7548cc','Подписан контрагентом','2025-09-25 12:27:56'),
  ('5262333239','СР-01-10-25','2025-10-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=2fc1e768-f401-47a9-bd31-f901b8660000&documentId=9cf971ec-779e-48d3-8f30-46874625cacf','Подписан контрагентом','2025-10-22 09:09:16'),
  ('9724057015','PM-22-10-25','2025-10-22','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=f3502f14-d662-4a6a-b954-303972564b64&documentId=e3d95b79-19a5-4969-a909-e58be441681f','Подписан контрагентом','2025-10-22 23:17:31'),
  ('7709950453','PM-20/10/2025','2025-10-20','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=83048b1a-de53-4142-9a89-611b34408281&documentId=f25ccc0a-9144-4d52-b641-046f26b9ecaf','Подписан контрагентом','2025-10-24 16:30:27'),
  ('7729591450','PM-24-10-25','2025-10-24','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=e2eb5a48-88c6-44f0-b558-b3cf54e1a89c&documentId=c02b9e63-94df-481f-9b67-6f16224a81e3','Подписан контрагентом','2025-10-28 20:49:54'),
  ('7723885213','РМ-18-12-25','2025-12-18','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=dd22d63f-0a2f-4750-b64e-1b009b12d6bd&documentId=11db875d-a461-4cf3-85b9-3294be4c7af8','Подписан контрагентом','2025-12-19 12:54:01'),
  ('7733727061','РМ-21-11-25','2025-11-21','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=f6c56149-ac56-469f-a9c2-3aceaf91af0d&documentId=44199ac3-21dc-400e-8154-b02d074104fd','Подписан контрагентом','2026-01-12 17:34:10'),
  ('772606496909','15-2026-77','2025-01-15','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=bd0bd6ab-2c24-4004-a2fd-94a6c3287d85&documentId=24e523f2-b362-4cdd-ac40-e1ce20b20865','Подписан контрагентом','2026-01-21 10:12:16'),
  ('7726362853','РМ-25-11-25','2025-11-25','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=4749bfb8-7d78-4b8a-8585-f49022783dc9&documentId=a46cc0b4-21c8-4a22-9d5f-39e38176ecae','Подписан контрагентом','2026-01-23 14:32:22'),
  ('5038114285','РМ-26-01-26','2026-01-26','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=b1ebb17d-f26e-4190-877b-c33a5dd24073&documentId=e93677e1-fdcd-4b4a-b291-166a1147c004','Подписан контрагентом','2026-02-05 18:18:59'),
  ('7714412348','РМ-24-02-26','2026-02-24','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=34b7be51-d2e5-4010-abd3-ba46b11e57cc&documentId=bd3ee3ed-cf0c-486f-a83b-d226b97303eb','Подписан контрагентом','2026-03-11 11:13:04'),
  ('7718287257','РМ-23-03-26','2026-03-23','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=ce426b3b-a82b-4792-8081-45f80c353b04&documentId=c5c73aff-e63f-462b-ac1d-1fb09b913e3e','Подписан контрагентом','2026-03-31 09:59:14'),
  ('3665823962','А-20-04-26','2026-04-20','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=430fb5cf-5e94-4e1b-9c89-c9cc419a9c2b&documentId=93f5e983-a92c-4977-9539-f1ee960afc24','Подписан контрагентом','2026-04-29 13:13:03'),
  ('1832007271','РП-22-04-26','2026-04-22','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=8535bc46-88f7-4226-a0b3-89481ccda166&documentId=77254e61-09c5-45e6-97a9-da4a316ce54a','Подписан контрагентом','2026-05-29 13:59:00'),
  ('7743299351','PM-05-05-26','2026-05-05','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=749f4f8c-87cb-4c7c-ba2d-06b44a7fc65c&documentId=f37ba637-9e48-4b6d-b3c4-3d34989d333e','Подписан контрагентом','2026-05-09 22:51:12'),
  ('7706811620','РМ-18-05-26','2026-05-18','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=76e6a442-f871-4d6b-951b-dbedcf48e27d&documentId=270e516b-aab3-49b0-8235-f5bac1a6bd87','Подписан контрагентом','2026-05-26 21:53:11'),
  ('2543102471','РП-15-05-26','2026-05-15','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=d8a9ce8c-fdf7-4fb5-aa6e-272cbe6601bf&documentId=f8a9648f-8b3f-4882-9fb9-307683d8b063','Подписан контрагентом','2026-06-22 04:13:47'),
  ('7728474136','РМ-01-05-26','2026-05-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=a11d0de6-1f02-4e16-bb15-32c23dd04dfb&documentId=4aeeb996-3055-48fb-ac5f-310c66f24535','Подписан контрагентом','2026-06-09 08:02:12'),
  ('7704774571','РМ-01-06-26','2026-06-01','https://diadoc.kontur.ru/143bcbfb-a011-4791-9316-981158fa5552/Document/Show?letterId=13ca9592-bcd0-467c-ae20-7466ce7c65e0&documentId=ff979063-8d53-4bde-a094-440dd21680f0','Подписан контрагентом','2026-06-23 15:43:46');

-- 3. UPDATE: tochnoe sovpadenie INN + nomer
UPDATE contracts c
SET
  contract_number = s.num,
  contract_date   = s.date_doc,
  document_link   = CASE WHEN (c.document_link IS NULL OR c.document_link = '') THEN s.link ELSE c.document_link END,
  edo_status      = s.status,
  edo_signed_at   = s.signed_at
FROM edo_stage s
WHERE c.inn = s.inn
  AND c.contract_number = s.num;

-- 4. UPDATE: pustye zapisi (contract_number IS NULL / '') — tol'ko esli unikal'naya zapis' s takim INN
UPDATE contracts c
SET
  contract_number = s.num,
  contract_date   = s.date_doc,
  document_link   = CASE WHEN (c.document_link IS NULL OR c.document_link = '') THEN s.link ELSE c.document_link END,
  edo_status      = s.status,
  edo_signed_at   = s.signed_at
FROM edo_stage s
WHERE c.inn = s.inn
  AND (c.contract_number IS NULL OR c.contract_number = '')
  AND (SELECT COUNT(*) FROM contracts c2
       WHERE c2.inn = s.inn
         AND (c2.contract_number IS NULL OR c2.contract_number = '')) = 1;

COMMIT;

-- Proverka
SELECT COUNT(*) AS obnovleno_vsego   FROM contracts WHERE edo_status IS NOT NULL;
SELECT COUNT(*) AS s_linkom          FROM contracts WHERE document_link LIKE '%diadoc%';
SELECT inn, contract_number, edo_status, LEFT(document_link,60)
FROM contracts WHERE edo_status = 'Требуется аннулирование';
DROP TABLE IF EXISTS edo_stage;