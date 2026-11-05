-- Execute with psql -X -v ON_ERROR_STOP=1, reviewed read-only credentials,
-- TLS and PGOPTIONS configuring automatize.audit_bucket for the application.
-- Output is restricted operational evidence, never public build output.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL search_path=pg_catalog,pg_temp;
SET LOCAL statement_timeout='15s';
SET LOCAL lock_timeout='3s';

SELECT pg_catalog.current_setting('transaction_read_only') AS read_only,
       pg_catalog.current_setting('server_version') AS server_version,
       NULLIF(pg_catalog.current_setting('automatize.audit_bucket',true),'') IS NOT NULL AS bucket_configured;

SELECT version_num FROM public.alembic_version;

SELECT n.nspname,c.relname,pg_catalog.pg_get_userbyid(c.relowner) AS owner,
       c.relrowsecurity,c.relforcerowsecurity,
       pg_catalog.row_security_active(c.oid) AS reader_is_filtered
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname IN ('public','storage') AND c.relkind IN ('r','p') ORDER BY 1,2;

SELECT n.nspname,c.relname,a.attname,pg_catalog.format_type(a.atttypid,a.atttypmod) AS type,
       a.attnotnull,pg_catalog.pg_get_expr(d.adbin,d.adrelid) AS default_expression
FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
LEFT JOIN pg_catalog.pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY c.relname,a.attnum;

SELECT c.relname,k.conname,k.contype,k.convalidated,k.condeferrable,k.condeferred,
       pg_catalog.pg_get_constraintdef(k.oid) AS definition
FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' ORDER BY c.relname,k.conname;

SELECT schemaname,tablename,indexname,indexdef FROM pg_catalog.pg_indexes
WHERE schemaname='public' ORDER BY tablename,indexname;

SELECT n.nspname,c.relname,acl.grantor,acl.grantee,acl.privilege_type,acl.is_grantable
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(coalesce(c.relacl,pg_catalog.acldefault('r',c.relowner))) acl
WHERE n.nspname IN ('public','storage') AND c.relkind='r' ORDER BY 1,2,4,5;

SELECT n.nspname,c.relname,a.attname,acl.grantee,acl.privilege_type,acl.is_grantable
FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(a.attacl) acl
WHERE n.nspname IN ('public','storage') AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2,3,4,5;

SELECT c.relname,r.rolname,
       pg_catalog.has_table_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') AS any_legacy_privilege,
       pg_catalog.has_any_column_privilege(r.oid,c.oid,'SELECT,INSERT,UPDATE,REFERENCES') AS any_column_privilege,
       CASE WHEN pg_catalog.current_setting('server_version_num')::integer>=170000
         THEN pg_catalog.has_table_privilege(r.oid,c.oid,'MAINTAIN') ELSE NULL END AS maintain
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
CROSS JOIN pg_catalog.pg_roles r
WHERE n.nspname='public' AND c.relkind='r' AND r.rolname IN ('anon','authenticated','service_role',current_user)
ORDER BY 1,2;

SELECT pg_catalog.pg_get_userbyid(d.defaclrole) AS creator,
       coalesce(n.nspname,'ALL_SCHEMAS') AS schema_name,d.defaclobjtype,
       acl.grantor,acl.grantee,acl.privilege_type,acl.is_grantable
FROM pg_catalog.pg_default_acl d LEFT JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace
CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) acl ORDER BY 1,2,3,5,6;

SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolinherit,rolcanlogin
FROM pg_catalog.pg_roles ORDER BY rolname;

SELECT pg_catalog.pg_get_userbyid(roleid) AS granted_role,
       pg_catalog.pg_get_userbyid(member) AS member_role,admin_option
FROM pg_catalog.pg_auth_members ORDER BY 1,2;

SELECT p.proname,p.prosecdef,p.proconfig,pg_catalog.pg_get_userbyid(p.proowner) AS owner,
       pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(pg_catalog.pg_get_functiondef(p.oid),'UTF8')),'hex') AS definition_sha256,
       acl.grantee,acl.privilege_type,acl.is_grantable
FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
LEFT JOIN LATERAL pg_catalog.aclexplode(coalesce(p.proacl,pg_catalog.acldefault('f',p.proowner))) acl ON true
WHERE n.nspname='public' AND p.proname IN
 ('bloquear_alteracao_aceite_formal','proteger_conclusao_pedido','proteger_auditoria_log') ORDER BY 1,6;

SELECT c.relname,t.tgname,t.tgenabled,p.proname,pg_catalog.pg_get_triggerdef(t.oid) AS definition
FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY 1,2;

SELECT schemaname,tablename,policyname,roles,cmd,permissive,qual,with_check
FROM pg_catalog.pg_policies WHERE schemaname IN ('public','storage') ORDER BY 1,2,3;

SELECT id,public FROM storage.buckets
WHERE id=pg_catalog.current_setting('automatize.audit_bucket',true);

WITH visibility AS (
 SELECT NULLIF(pg_catalog.current_setting('automatize.audit_bucket',true),'') IS NOT NULL
   AND NOT pg_catalog.row_security_active('storage.buckets'::regclass)
   AND NOT pg_catalog.row_security_active('storage.objects'::regclass)
   AND NOT pg_catalog.row_security_active('public.anexos'::regclass)
   AND NOT pg_catalog.row_security_active('public.pedidos'::regclass)
   AND EXISTS(SELECT 1 FROM storage.buckets WHERE id=pg_catalog.current_setting('automatize.audit_bucket',true)
              AND NOT public) AS complete
)
SELECT complete AS full_visibility_required,
 CASE WHEN complete THEN (SELECT count(*) FROM storage.objects
   WHERE bucket_id=pg_catalog.current_setting('automatize.audit_bucket',true)) ELSE NULL END AS catalog_objects,
 CASE WHEN complete THEN (SELECT count(*) FROM storage.objects o
   WHERE o.bucket_id=pg_catalog.current_setting('automatize.audit_bucket',true)
     AND NOT EXISTS(SELECT 1 FROM public.anexos a WHERE a.caminho_storage=o.name)) ELSE NULL END AS objects_without_reference,
 CASE WHEN complete THEN (SELECT count(*) FROM public.anexos a
   WHERE NOT EXISTS(SELECT 1 FROM storage.objects o WHERE o.name=a.caminho_storage
     AND o.bucket_id=pg_catalog.current_setting('automatize.audit_bucket',true))) ELSE NULL END AS references_without_object
FROM visibility;

SELECT true AS diagnostic_only,false AS deployment_authorized,false AS cleanup_authorized;
ROLLBACK;
