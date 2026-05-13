-- Chinook_MySql.sql creates a database called `Chinook`. We standardise on `chinook`.
-- This script runs after the dump, so `Chinook` exists.

CREATE DATABASE IF NOT EXISTS chinook
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

-- Move all tables from Chinook -> chinook. Lowercase schema is friendlier on Linux.
-- If chinook is empty and Chinook has tables, rename them across.
DELIMITER //
CREATE PROCEDURE move_chinook_tables()
BEGIN
    DECLARE done INT DEFAULT 0;
    DECLARE tname VARCHAR(128);
    DECLARE cur CURSOR FOR
        SELECT TABLE_NAME FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = 'Chinook';
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = 1;
    OPEN cur;
    read_loop: LOOP
        FETCH cur INTO tname;
        IF done THEN LEAVE read_loop; END IF;
        SET @s = CONCAT('RENAME TABLE Chinook.`', tname, '` TO chinook.`', tname, '`');
        PREPARE stmt FROM @s; EXECUTE stmt; DEALLOCATE PREPARE stmt;
    END LOOP;
    CLOSE cur;
END//
DELIMITER ;

CALL move_chinook_tables();
DROP PROCEDURE move_chinook_tables;
DROP DATABASE IF EXISTS Chinook;

-- Readonly user
CREATE USER IF NOT EXISTS 'readonly_user'@'%' IDENTIFIED BY 'readonly_pw';
GRANT SELECT ON chinook.* TO 'readonly_user'@'%';
FLUSH PRIVILEGES;
